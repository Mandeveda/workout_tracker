// Service Worker для Workout Tracker
const CACHE_NAME = 'workout-tracker-v1';
const STATIC_CACHE = 'static-v1';
const DYNAMIC_CACHE = 'dynamic-v1';

// Файлы для кэширования при первом запуске
const STATIC_FILES = [
    '/',
    '/static/styles.css',
    '/static/js/csrf.js',
    '/static/manifest.json',
    // Добавьте другие статические файлы
];

// Установка Service Worker
self.addEventListener('install', event => {
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then(cache => {
                console.log('Кэширование статики...');
                return cache.addAll(STATIC_FILES);
            })
            .then(() => self.skipWaiting())
    );
});

// Активация
self.addEventListener('activate', event => {
    event.waitUntil(
        caches.keys()
            .then(keys => {
                return Promise.all(
                    keys.filter(key => key !== STATIC_CACHE && key !== DYNAMIC_CACHE)
                        .map(key => caches.delete(key))
                );
            })
            .then(() => self.clients.claim())
    );
});

// Обработка запросов (стратегия: сначала кэш, потом сеть)
self.addEventListener('fetch', event => {
    // Пропускаем запросы к API (чтобы не кэшировать данные)
    if (event.request.url.includes('/api/') || 
        event.request.url.includes('/auth/') ||
        event.request.url.includes('/workouts/')) {
        return;
    }
    
    event.respondWith(
        caches.match(event.request)
            .then(cachedResponse => {
                if (cachedResponse) {
                    return cachedResponse;
                }
                return fetch(event.request)
                    .then(response => {
                        // Кэшируем только успешные ответы
                        if (!response || response.status !== 200) {
                            return response;
                        }
                        const responseToCache = response.clone();
                        caches.open(DYNAMIC_CACHE)
                            .then(cache => {
                                cache.put(event.request, responseToCache);
                            });
                        return response;
                    })
                    .catch(() => {
                        // Если нет сети и нет кэша — показываем офлайн-страницу
                        return caches.match('/offline.html');
                    });
            })
    );
});