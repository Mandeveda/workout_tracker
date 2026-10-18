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
