// Service worker Tracker Workout. Отдаётся с корня сайта (/sw.js), чтобы управлять всеми страницами.
//
// Что кэшируется:
//   - офлайн-страница — заранее, чтобы показать её без сети;
//   - оформление, скрипты, иконки (/static/…) — «из кэша, обновляя в фоне»;
//   - библиотеки и шрифты с CDN (версии зафиксированы) — «сначала кэш».
// Страницы с данными НЕ кэшируются: всегда из сети, без сети — офлайн-страница.
// Так после выхода на общем устройстве не покажется чужая страница
// и формы не получат устаревший CSRF-токен.
//
// При изменении этого файла увеличьте VERSION — старые кэши удалятся.
const VERSION = 'v2';
const STATIC_CACHE = `tw-static-${VERSION}`;
const OFFLINE_URL = '/offline';
const PRECACHE = [OFFLINE_URL, '/static/icons/launchericon-192x192.png'];
const CDN_HOSTS = ['cdn.jsdelivr.net', 'fonts.googleapis.com', 'fonts.gstatic.com'];

self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => cache.addAll(PRECACHE))
            .then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(keys => Promise.all(keys.filter(k => k !== STATIC_CACHE).map(k => caches.delete(k))))
            .then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', event => {
    const request = event.request;
    if (request.method !== 'GET') return;            // формы и сохранения — только напрямую в сеть
    const url = new URL(request.url);

    // Переходы по страницам: всегда сеть; нет сети — офлайн-страница
    if (request.mode === 'navigate') {
        event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_URL)));
        return;
    }

    // Своё оформление и скрипты: сразу из кэша, параллельно обновляем
    if (url.origin === self.location.origin && url.pathname.startsWith('/static/')) {
        event.respondWith(staleWhileRevalidate(request));
        return;
    }

    // Библиотеки и шрифты с CDN: версии зафиксированы, файлы не меняются
    if (CDN_HOSTS.includes(url.hostname)) {
        event.respondWith(cacheFirst(request));
    }
    // Остальное (данные для графиков и т. п.) — обычным запросом, без кэша
});

function staleWhileRevalidate(request) {
    return caches.open(STATIC_CACHE).then(cache =>
        cache.match(request).then(cached => {
            const network = fetch(request).then(response => {
                if (response.ok) cache.put(request, response.clone());
                return response;
            }).catch(() => cached);
            return cached || network;
        })
    );
}

function cacheFirst(request) {
    return caches.open(STATIC_CACHE).then(cache =>
        cache.match(request).then(cached => cached || fetch(request).then(response => {
            if (response.ok || response.type === 'opaque') cache.put(request, response.clone());
            return response;
        }))
    );
}
