"""Этап 4 плана: установка как приложения (PWA)"""
import json
import os

from conftest import login

STATIC = os.path.join(os.path.dirname(__file__), '..', 'app', 'static')


def test_manifest_is_installable_and_icons_exist():
    """План 4.4: в манифесте были ссылки на несуществующие иконки"""
    with open(os.path.join(STATIC, 'manifest.json'), encoding='utf-8') as f:
        manifest = json.load(f)
    assert manifest['display'] == 'standalone' and manifest['scope'] == '/'
    assert manifest['start_url'].startswith('/dashboard')
    sizes = {i['sizes'] for i in manifest['icons'] if 'any' in i['purpose']}
    assert {'192x192', '512x512'} <= sizes                                   # требование Chrome для установки
    assert any(i['purpose'] == 'maskable' for i in manifest['icons'])
    for icon in manifest['icons'] + [i for s in manifest['shortcuts'] for i in s['icons']]:
        assert os.path.exists(os.path.join(STATIC, icon['src'].removeprefix('/static/'))), icon['src']


def test_service_worker_served_from_root(client):
    """План 4.1: из /static/sw.js он управлял только /static/, а не страницами"""
    response = client.get('/sw.js')
    assert response.status_code == 200
    assert response.mimetype == 'application/javascript'
    assert 'no-cache' in response.headers['Cache-Control']
    assert "request.mode === 'navigate'" in response.get_data(as_text=True)


def test_service_worker_does_not_cache_pages():
    """План 4.2: страницы с данными не кэшируются — только статика и CDN"""
    with open(os.path.join(STATIC, 'sw.js'), encoding='utf-8') as f:
        source = f.read()
    assert "if (request.method !== 'GET') return;" in source
    assert "fetch(request).catch(() => caches.match(OFFLINE_URL))" in source


def test_offline_page_is_standalone_and_anonymous(client, make_user):
    """План 4.3: офлайн-страница кэшируется для устройства — без имени пользователя и внешних файлов"""
    make_user('anna_secret')
    login(client, 'anna_secret')
    page = client.get('/offline').get_data(as_text=True)
    assert 'Нет соединения' in page
    assert 'anna_secret' not in page
    assert 'cdn.jsdelivr' not in page and 'fonts.googleapis' not in page


def test_pages_have_install_wiring(client):
    page = client.get('/').get_data(as_text=True)
    assert 'rel="manifest"' in page and 'data-install' in page and 'installIosModal' in page
    assert 'installAndroidModal' in page and 'package=com.android.chrome' in page
    assert '/static/icons/apple-touch-icon.png' in page
    assert "register('/static/sw.js')" not in page
    assert '/static/js/pwa.js?v=' in page                 # версия у статики сбрасывает кэш после обновления
