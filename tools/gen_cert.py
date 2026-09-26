# -*- coding: utf-8 -*-
"""生成自签根证书与服务器证书。

只依赖 Python 标准库：部署机（含 Windows 7）不需要安装 openssl，
也不需要 PowerShell 的 PKI 模块。

用法：
    python tools/gen_cert.py                         自动探测本机 IP 与主机名
    python tools/gen_cert.py --san 192.168.1.10,ocr   追加额外的主机名/IP
    python tools/gen_cert.py --force                  覆盖已存在的证书
    python tools/gen_cert.py --days 3650 --key-bits 2048

产物（默认写入 <项目>/data/certs）：
    ca.key ca.crt       根证书私钥与证书（PEM）
    ca.cer              根证书（DER，供 Windows 客户端导入信任）
    server.key server.crt  服务器证书（含 SAN 与 serverAuth 用途）
"""

import argparse
import base64
import datetime
import hashlib
import ipaddress
import os
import random
import secrets
import socket
import sys
from pathlib import Path

# --------------------------------------------------------------------------
# ASN.1 DER 基础编码
# --------------------------------------------------------------------------


def _length(size):
    if size < 0x80:
        return bytes([size])
    body = b''
    while size:
        body = bytes([size & 0xFF]) + body
        size >>= 8
    return bytes([0x80 | len(body)]) + body


def tlv(tag, content):
    return bytes([tag]) + _length(len(content)) + content


def der_int(value):
    if value == 0:
        return tlv(0x02, b'\x00')
    if value < 0:
        raise ValueError('本实现只支持非负整数')
    body = value.to_bytes((value.bit_length() + 7) // 8, 'big')
    if body[0] & 0x80:
        body = b'\x00' + body
    return tlv(0x02, body)


def der_seq(*items):
    return tlv(0x30, b''.join(items))


def der_set(*items):
    return tlv(0x31, b''.join(items))


def der_null():
    return tlv(0x05, b'')


def der_bool(value):
    return tlv(0x01, b'\xff' if value else b'\x00')


def der_octet(data):
    return tlv(0x04, data)


def der_bitstring(data, unused=0):
    return tlv(0x03, bytes([unused]) + data)


def der_printable(text):
    return tlv(0x13, text.encode('ascii'))


def der_utf8(text):
    return tlv(0x0C, text.encode('utf-8'))


def der_utctime(moment):
    if moment.year >= 2050:
        raise ValueError('本实现用 UTCTime，notAfter 需早于 2050 年')
    stamp = moment.strftime('%y%m%d%H%M%S')
    return tlv(0x17, (stamp + 'Z').encode('ascii'))


def der_oid(dotted):
    parts = [int(item) for item in dotted.split('.')]
    body = bytearray([40 * parts[0] + parts[1]])
    for value in parts[2:]:
        chunk = []
        while True:
            chunk.insert(0, value & 0x7F)
            value >>= 7
            if value == 0:
                break
        for index, byte in enumerate(chunk):
            body.append(byte | (0x80 if index < len(chunk) - 1 else 0))
    return tlv(0x06, bytes(body))


def der_context(number, content, constructed=True):
    """[n] 显式包装（EXPLICIT）。"""
    return tlv((0xA0 if constructed else 0x80) | number, content)


def pem(label, data):
    body = base64.encodebytes(data).decode('ascii').strip()
    return '-----BEGIN %s-----\n%s\n-----END %s-----\n' % (label, body, label)


# --------------------------------------------------------------------------
# RSA 密钥
# --------------------------------------------------------------------------

_SMALL_PRIMES = (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47)


def _is_probable_prime(number, rounds=16):
    if number < 2:
        return False
    for prime in _SMALL_PRIMES:
        if number % prime == 0:
            return number == prime
    rest = number - 1
    shift = 0
    while rest % 2 == 0:
        rest //= 2
        shift += 1
    for _ in range(rounds):
        base = random.randrange(2, number - 1)
        value = pow(base, rest, number)
        if value in (1, number - 1):
            continue
        for _ in range(shift - 1):
            value = pow(value, 2, number)
            if value == number - 1:
                break
        else:
            return False
    return True


def _generate_prime(bits):
    while True:
        candidate = random.getrandbits(bits) | (1 << (bits - 1)) | 1
        if _is_probable_prime(candidate):
            return candidate


def generate_rsa_key(bits=2048):
    exponent = 65537
    while True:
        prime_a = _generate_prime(bits // 2)
        prime_b = _generate_prime(bits - bits // 2)
        if prime_a == prime_b:
            continue
        modulus = prime_a * prime_b
        if modulus.bit_length() != bits:
            continue
        phi = (prime_a - 1) * (prime_b - 1)
        if phi % exponent == 0:
            continue
        private = pow(exponent, -1, phi)
        high, low = (prime_a, prime_b) if prime_a > prime_b else (prime_b, prime_a)
        return {
            'n': modulus,
            'e': exponent,
            'd': private,
            'p': high,
            'q': low,
            'dp': private % (high - 1),
            'dq': private % (low - 1),
            'qinv': pow(low, -1, high),
        }


def rsa_private_der(key):
    return der_seq(der_int(0), der_int(key['n']), der_int(key['e']), der_int(key['d']),
                   der_int(key['p']), der_int(key['q']), der_int(key['dp']),
                   der_int(key['dq']), der_int(key['qinv']))


def rsa_public_der(key):
    return der_seq(der_int(key['n']), der_int(key['e']))


def pkcs8_private_der(key):
    return der_seq(der_int(0),
                   der_seq(der_oid('1.2.840.113549.1.1.1'), der_null()),
                   der_octet(rsa_private_der(key)))


def private_key_pem(key):
    return pem('PRIVATE KEY', pkcs8_private_der(key))


# --------------------------------------------------------------------------
# X.509 证书
# --------------------------------------------------------------------------

NAME_OIDS = {
    'C': '2.5.4.6',
    'O': '2.5.4.10',
    'OU': '2.5.4.11',
    'CN': '2.5.4.3',
}

SHA256_WITH_RSA = '1.2.840.113549.1.1.11'
RSA_ENCRYPTION = '1.2.840.113549.1.1.1'
EXT_BASIC_CONSTRAINTS = '2.5.29.19'
EXT_KEY_USAGE = '2.5.29.15'
EXT_EXT_KEY_USAGE = '2.5.29.37'
EXT_SUBJECT_ALT_NAME = '2.5.29.17'
EXT_SUBJECT_KEY_ID = '2.5.29.14'
EXT_AUTHORITY_KEY_ID = '2.5.29.35'
SERVER_AUTH = '1.3.6.1.5.5.7.3.1'

KEY_USAGE_BITS = {
    'digitalSignature': 0,
    'nonRepudiation': 1,
    'keyEncipherment': 2,
    'dataEncipherment': 3,
    'keyAgreement': 4,
    'keyCertSign': 5,
    'cRLSign': 6,
}


def build_ski(key):
    """Subject Key Identifier：公钥 DER 的 SHA-1（RFC 5280 方法 1）。

    没有它 OpenSSL（以及部分浏览器）会以
    "Missing Authority Key Identifier" 拒绝校验。
    """
    return hashlib.sha1(rsa_public_der(key)).digest()


def build_name(parts):
    """parts 例如 {'C': 'CN', 'O': 'My OCR', 'CN': 'ocr-server'}。"""
    rdns = []
    for field_name in ('C', 'O', 'OU', 'CN'):
        value = parts.get(field_name)
        if not value:
            continue
        text = str(value)
        encoded = der_printable(text) if field_name == 'C' else der_utf8(text)
        rdns.append(der_set(der_seq(der_oid(NAME_OIDS[field_name]), encoded)))
    if not rdns:
        raise ValueError('证书名称不能为空')
    return der_seq(b''.join(rdns))


def build_key_usage(names):
    highest = max(KEY_USAGE_BITS[name] for name in names)
    size = highest // 8 + 1
    buffer = bytearray(size)
    for name in names:
        bit = KEY_USAGE_BITS[name]
        buffer[bit // 8] |= 0x80 >> (bit % 8)
    unused = size * 8 - (highest + 1)
    return der_bitstring(bytes(buffer), unused)


def build_san(dns_names, ip_addresses):
    entries = b''
    for name in dns_names:
        entries += tlv(0x82, name.encode('ascii'))
    for address in ip_addresses:
        entries += tlv(0x87, ipaddress.ip_address(address).packed)
    return der_seq(entries)


def build_extension(oid, critical, value):
    parts = [der_oid(oid)]
    if critical:
        parts.append(der_bool(True))
    parts.append(der_octet(value))
    return der_seq(b''.join(parts))


def sign_pkcs1_sha256(payload, key):
    """EMSA-PKCS1-v1_5 + SHA-256 签名。"""
    digest_info = bytes.fromhex('3031300d060960864801650304020105000420')
    digest_info += hashlib.sha256(payload).digest()
    size = (key['n'].bit_length() + 7) // 8
    if len(digest_info) > size - 11:
        raise ValueError('RSA 密钥长度不足')
    padded = b'\x00\x01' + b'\xff' * (size - len(digest_info) - 3) + b'\x00' + digest_info
    signature = pow(int.from_bytes(padded, 'big'), key['d'], key['n'])
    return signature.to_bytes(size, 'big')


def build_certificate(subject_parts, issuer_parts, subject_key, issuer_key,
                      serial, not_before, not_after, is_ca,
                      key_usage, dns_names=(), ip_addresses=(), extended_usage=(),
                      path_length=None):
    basics = der_bool(True)
    if path_length is not None:
        basics += der_int(path_length)

    extensions = [
        build_extension(EXT_SUBJECT_KEY_ID, False, der_octet(build_ski(subject_key))),
        build_extension(EXT_AUTHORITY_KEY_ID, False,
                        der_seq(tlv(0x80, build_ski(issuer_key)))),
        build_extension(EXT_BASIC_CONSTRAINTS, True, der_seq(basics)),
        build_extension(EXT_KEY_USAGE, True, build_key_usage(key_usage)),
    ]
    if dns_names or ip_addresses:
        extensions.append(build_extension(
            EXT_SUBJECT_ALT_NAME, False, build_san(tuple(dns_names), tuple(ip_addresses))))
    if extended_usage:
        extensions.append(build_extension(
            EXT_EXT_KEY_USAGE, False,
            der_seq(b''.join(der_oid(item) for item in extended_usage))))

    tbs = der_seq(
        der_context(0, der_int(2)),
        der_int(serial),
        der_seq(der_oid(SHA256_WITH_RSA), der_null()),
        build_name(issuer_parts),
        der_seq(der_utctime(not_before), der_utctime(not_after)),
        build_name(subject_parts),
        der_seq(der_seq(der_oid(RSA_ENCRYPTION), der_null()),
                der_bitstring(rsa_public_der(subject_key))),
        der_context(3, der_seq(b''.join(extensions))),
    )
    signature = sign_pkcs1_sha256(tbs, issuer_key)
    return der_seq(tbs, der_seq(der_oid(SHA256_WITH_RSA), der_null()),
                   der_bitstring(signature))


# --------------------------------------------------------------------------
# 命令行
# --------------------------------------------------------------------------


def detect_names():
    """探测本机主机名与 IPv4 地址。"""
    dns_names = {'localhost'}
    ip_addresses = {'127.0.0.1'}
    try:
        host = socket.gethostname()
        if host:
            dns_names.add(host)
        fqdn = socket.getfqdn()
        if fqdn:
            dns_names.add(fqdn)
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('8.8.8.8', 53))
            ip_addresses.add(probe.getsockname()[0])
        finally:
            probe.close()
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip_addresses.add(info[4][0])
    except OSError:
        pass
    return sorted(dns_names), sorted(ip_addresses)


def split_san(text):
    dns_names = []
    ip_addresses = []
    for item in str(text).replace(';', ',').split(','):
        item = item.strip()
        if not item:
            continue
        try:
            ipaddress.ip_address(item)
            ip_addresses.append(item)
        except ValueError:
            dns_names.append(item)
    return dns_names, ip_addresses


def write_text(path, text):
    with open(str(path), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(text)


def write_binary(path, data):
    with open(str(path), 'wb') as handle:
        handle.write(data)


def _force_utf8_output():
    """保留平台控制台编码，只把无法编码的字符替换掉。

    与批处理脚本的输出编码保持一致，重定向到同一个文件时不会出现两种编码混排。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.reconfigure(errors='replace')
        except (AttributeError, ValueError, OSError):
            pass

def main(argv=None):
    parser = argparse.ArgumentParser(description='生成自签根证书与服务器证书')
    parser.add_argument('--data-dir', default=None, help='数据目录，默认 <项目>/data')
    parser.add_argument('--san', default='', help='额外的主机名/IP，逗号分隔')
    parser.add_argument('--days', type=int, default=3650, help='有效期天数，默认 3650')
    parser.add_argument('--key-bits', type=int, default=2048, help='RSA 位数，默认 2048')
    parser.add_argument('--common-name', default='', help='服务器证书 CN，默认取首个 SAN')
    parser.add_argument('--force', action='store_true', help='覆盖已存在的证书')
    args = parser.parse_args(argv)
    _force_utf8_output()

    root = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else (root / 'data')
    cert_dir = data_dir / 'certs'
    cert_dir.mkdir(parents=True, exist_ok=True)

    targets = {
        'ca_key': cert_dir / 'ca.key',
        'ca_crt': cert_dir / 'ca.crt',
        'ca_cer': cert_dir / 'ca.cer',
        'server_key': cert_dir / 'server.key',
        'server_crt': cert_dir / 'server.crt',
    }
    existing = [path.name for path in targets.values() if path.is_file()]
    if existing and not args.force:
        print('[跳过] 证书已存在：%s' % '、'.join(existing))
        print('       如需重新生成请加 --force')
        return 0

    if args.key_bits < 2048:
        print('[错误] RSA 位数至少 2048')
        return 1

    dns_names, ip_addresses = detect_names()
    extra_dns, extra_ips = split_san(args.san)
    for name in extra_dns:
        if name not in dns_names:
            dns_names.append(name)
    for address in extra_ips:
        if address not in ip_addresses:
            ip_addresses.append(address)
    dns_names = sorted(set(dns_names))
    ip_addresses = sorted(set(ip_addresses), key=lambda item: ipaddress.ip_address(item))

    common_name = args.common_name or (dns_names[0] if dns_names else ip_addresses[0])
    now = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None, microsecond=0)
    not_before = now - datetime.timedelta(days=1)
    not_after = now + datetime.timedelta(days=args.days)

    print('正在生成 RSA 密钥（%d 位），请稍候…' % args.key_bits)
    ca_key = generate_rsa_key(args.key_bits)
    server_key = generate_rsa_key(args.key_bits)

    ca_parts = {'C': 'CN', 'O': 'My OCR Internal CA', 'CN': 'My OCR Internal CA'}
    ca_cert = build_certificate(
        subject_parts=ca_parts, issuer_parts=ca_parts,
        subject_key=ca_key, issuer_key=ca_key,
        serial=secrets.randbits(64) | 1,
        not_before=not_before, not_after=not_after,
        is_ca=True, key_usage=('keyCertSign', 'cRLSign', 'digitalSignature'),
        path_length=0)

    server_parts = {'C': 'CN', 'O': 'My OCR', 'CN': common_name}
    server_cert = build_certificate(
        subject_parts=server_parts, issuer_parts=ca_parts,
        subject_key=server_key, issuer_key=ca_key,
        serial=secrets.randbits(64) | 1,
        not_before=not_before, not_after=not_after,
        is_ca=False,
        key_usage=('digitalSignature', 'keyEncipherment'),
        dns_names=dns_names, ip_addresses=ip_addresses,
        extended_usage=(SERVER_AUTH,))

    write_text(targets['ca_key'], private_key_pem(ca_key))
    write_text(targets['ca_crt'], pem('CERTIFICATE', ca_cert))
    write_text(targets['server_key'], private_key_pem(server_key))
    write_text(targets['server_crt'], pem('CERTIFICATE', server_cert))
    write_binary(targets['ca_cer'], ca_cert)  # DER，供 Windows 导入

    if os.name != 'nt':
        for path in (targets['ca_key'], targets['server_key']):
            try:
                os.chmod(str(path), 0o600)
            except OSError:
                pass

    print('已生成：')
    for name in ('ca.crt', 'ca.cer', 'ca.key', 'server.crt', 'server.key'):
        print('  %s' % (cert_dir / name))
    print('服务器证书 CN：%s' % common_name)
    print('生效的主机名：%s' % '、'.join(dns_names))
    print('生效的 IP    ：%s' % '、'.join(ip_addresses))
    print('有效期至     ：%s' % not_after.strftime('%Y-%m-%d'))
    print('')
    print('客户端首次使用 https 前，请导入根证书（任选其一）：')
    print('  1) 浏览器访问 https://<服务器IP>:8443/api/system/root-cert 下载后双击导入"受信任的根证书颁发机构"')
    print('  2) 直接使用 %s' % targets['ca_cer'])
    print('注意：私钥文件（%s、%s）不可外发。' % ('ca.key', 'server.key'))
    return 0


if __name__ == '__main__':
    sys.exit(main())