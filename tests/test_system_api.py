# -*- coding: utf-8 -*-
"""系统接口与静态资源托管测试。"""


def test_status_requires_login(client):
    assert client.get('/api/system/status').status_code == 401


def test_status_reports_offline_engine(logged_in):
    client, _token = logged_in
    response = client.get('/api/system/status')
    assert response.status_code == 200
    payload = response.get_json()['data']

    assert payload['umi']['online'] is False
    assert payload['umi']['process_running'] is False
    assert payload['umi']['autostart'] is False
    assert payload['queue']['pending'] == 0
    assert payload['queue']['running'] == 0
    assert payload['workers'] == 1
    assert payload['disk']['free'] > 0
    assert payload['https']['cert_exists'] is False
    assert payload['app_version']


def test_ocr_options_unavailable_without_engine(logged_in):
    client, _token = logged_in
    response = client.get('/api/system/ocr-options')
    assert response.status_code == 503
    assert response.get_json()['error']['code'] == 'umi_unavailable'


def test_root_cert_missing_returns_404(client):
    response = client.get('/api/system/root-cert')
    assert response.status_code == 404
    assert response.get_json()['error']['code'] == 'not_found'


def test_unknown_api_path_returns_json_404(client):
    response = client.get('/api/does-not-exist')
    assert response.status_code == 404
    assert response.get_json()['error']['code'] == 'not_found'


def test_placeholder_page_when_frontend_not_built(client):
    response = client.get('/')
    assert response.status_code == 200
    assert '后端已启动' in response.get_data(as_text=True)


def test_serves_built_frontend(app_factory, tmp_path):
    """前端已构建时：根路径返回首页，静态资源可下载，未知前端路由回落到首页。"""
    dist = tmp_path / 'dist'
    (dist / 'assets').mkdir(parents=True)
    (dist / 'index.html').write_text(
        '<!doctype html><div id="app"></div><script src="/assets/app.js"></script>',
        encoding='utf-8')
    (dist / 'assets' / 'app.js').write_text('console.log(1)', encoding='utf-8')

    client = app_factory(frontend_dist_dir=str(dist)).test_client()

    index = client.get('/')
    assert index.status_code == 200
    assert 'id="app"' in index.get_data(as_text=True)

    asset = client.get('/assets/app.js')
    assert asset.status_code == 200
    assert 'console.log(1)' in asset.get_data(as_text=True)
    assert asset.headers['Content-Type'].startswith('application/javascript')

    deep = client.get('/some/deep/route')
    assert deep.status_code == 200
    assert 'id="app"' in deep.get_data(as_text=True)

    assert client.get('/api/nope').status_code == 404

def test_static_assets_use_correct_mime_types(app_factory, tmp_path):
    """静态资源必须用正确的 MIME 类型返回。

    Windows 注册表常把 .js 登记成 text/plain，一旦照抄，浏览器会拒绝加载
    ES 模块并导致页面白屏，因此这里显式锁定几种关键类型。
    """
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<!doctype html>ok', encoding='utf-8')
    (dist / 'app.js').write_text('export default 1', encoding='utf-8')
    (dist / 'app.css').write_text('body{}', encoding='utf-8')
    (dist / 'data.json').write_text('{}', encoding='utf-8')
    (dist / 'logo.svg').write_text('<svg/>', encoding='utf-8')

    client = app_factory(frontend_dist_dir=str(dist)).test_client()

    assert client.get('/app.js').headers['Content-Type'].startswith('application/javascript')
    assert client.get('/app.css').headers['Content-Type'].startswith('text/css')
    assert client.get('/data.json').headers['Content-Type'].startswith('application/json')
    assert client.get('/logo.svg').headers['Content-Type'].startswith('image/svg+xml')