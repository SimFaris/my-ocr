# -*- coding: utf-8 -*-
"""历史检索测试。"""

import io

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 40


def make_job_with_text(api, title, file_name, text):
    job_id = api.post('/api/jobs', json={'title': title, 'source_type': 'image'}
                      ).get_json()['data']['job']['id']
    item_id = api.post('/api/jobs/%s/items' % job_id,
                       data={'file': (io.BytesIO(PNG), file_name)},
                       content_type='multipart/form-data').get_json()['data']['item']['id']
    api.put('/api/items/%s/text' % item_id, json={'text': text})
    return job_id, item_id


def test_search_requires_keyword(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    assert api.get('/api/search').status_code == 400
    assert api.get('/api/search?q=%20').status_code == 400


def test_search_matches_title_filename_and_preview(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    job_id, item_id = make_job_with_text(api, '九月报销单据', '发票-001.png', '增值税电子普通发票 金额 128.00 元')
    make_job_with_text(api, '无关任务', 'other.png', '这是一些无关的文字')

    by_title = api.get('/api/search?q=报销').get_json()['data']
    assert [job['id'] for job in by_title['jobs']] == [job_id]

    by_name = api.get('/api/search?q=发票-001').get_json()['data']
    assert [item['id'] for item in by_name['items']] == [item_id]
    assert by_name['items'][0]['job_title'] == '九月报销单据'

    by_text = api.get('/api/search?q=增值税').get_json()['data']
    assert [item['id'] for item in by_text['items']] == [item_id]
    assert '增值税' in by_text['items'][0]['snippet']
    assert by_text['note']


def test_search_is_scoped_to_own_jobs(app, api_client, admin, make_user):
    admin_api = api_client(admin['username'], admin['password'])
    make_job_with_text(admin_api, '管理员的报销单', 'a.png', '内部资料')

    other = make_user('bob')
    bob_api = api_client(other['username'], other['password'])
    payload = bob_api.get('/api/search?q=报销').get_json()['data']
    assert payload['jobs'] == []
    assert payload['items'] == []

    # 管理员可以看全部
    payload_all = admin_api.get('/api/search?q=报销&scope=all').get_json()['data']
    assert len(payload_all['jobs']) == 1


def test_search_snippet_truncation(api_client, admin):
    api = api_client(admin['username'], admin['password'])
    long_text = '前置内容' * 30 + '关键目标' + '后置内容' * 30
    make_job_with_text(api, '片段测试', 'b.png', long_text)

    payload = api.get('/api/search?q=关键目标').get_json()['data']
    snippet = payload['items'][0]['snippet']
    assert '关键目标' in snippet
    assert len(snippet) < len(long_text)
    assert snippet.startswith('…')