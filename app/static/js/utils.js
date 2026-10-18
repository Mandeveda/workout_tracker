// static/js/utils.js — общие функции для страниц

// Экранирует текст для вставки в HTML (в том числе внутрь атрибутов в кавычках)
function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

// Возвращает URL, только если это http(s)-ссылка, иначе пустую строку
// (защита от javascript: и прочих опасных схем)
function safeUrl(url) {
    if (!url) return '';
    try {
        const parsed = new URL(url, window.location.origin);
        return ['http:', 'https:'].includes(parsed.protocol) ? parsed.href : '';
    } catch (e) {
        return '';
    }
}

// Подтверждение перед отправкой формы: <form data-confirm="Удалить?">
// Текст берётся из атрибута, а не из onclick, поэтому данные (названия) не попадают в JS-код
document.addEventListener('submit', function (event) {
    const message = event.target.dataset ? event.target.dataset.confirm : null;
    if (message && !confirm(message)) {
        event.preventDefault();
    }
});

// Переключатель темы (кнопки .js-theme-toggle). Выбор запоминается в браузере
document.addEventListener('click', function (event) {
    if (!event.target.closest('.js-theme-toggle')) return;
    const html = document.documentElement;
    const next = html.getAttribute('data-bs-theme') === 'light' ? 'dark' : 'light';
    html.setAttribute('data-bs-theme', next);
    try { localStorage.setItem('tw-theme', next); } catch (e) {}
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', next === 'light' ? '#f7f2ea' : '#121110');
});

// Сообщения об успехе и информация скрываются сами через 5 секунд
document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.alert.js-autohide').forEach(function (el) {
        setTimeout(function () {
            if (window.bootstrap && bootstrap.Alert) bootstrap.Alert.getOrCreateInstance(el).close();
            else el.remove();
        }, 5000);
    });
});
