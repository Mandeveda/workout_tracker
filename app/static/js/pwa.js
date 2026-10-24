// static/js/pwa.js — установка сайта как приложения и регистрация service worker
//
// Кнопки [data-install] скрыты по умолчанию и показываются, только когда установка возможна:
//   - Android / Chrome / Edge: браузер присылает событие beforeinstallprompt — по кнопке
//     вызываем его стандартное окно установки;
//   - iPhone / iPad (Safari): такого события нет — кнопка открывает инструкцию
//     «Поделиться → На экран Домой» (#installIosModal);
//   - Android в Яндекс Браузере, браузере Xiaomi, Firefox и т. п.: они кладут на экран обычный
//     ярлык, который открывает сайт внутри браузера, — кнопка открывает инструкцию
//     «откройте в Chrome» (#installAndroidModal).
// В уже установленном приложении (display-mode: standalone) кнопок нет.
(function () {
    const isStandalone = window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
    const isIos = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
                  (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);   // iPad с iPadOS 13+
    const isAndroid = /android/i.test(navigator.userAgent);
    const isShortcutOnlyBrowser = isAndroid && /YaBrowser|YaApp|MiuiBrowser|XiaoMi|Firefox|OPR|UCBrowser|HeyTapBrowser/i.test(navigator.userAgent);
    let deferredPrompt = null;

    function showButtons(show) {
        document.querySelectorAll('[data-install]').forEach(el => { el.hidden = !show; });
    }

    if ('serviceWorker' in navigator) {
        window.addEventListener('load', function () {
            navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => {});
            // Раньше service worker регистрировался из /static/ и ничем не управлял — убираем его
            navigator.serviceWorker.getRegistrations().then(regs => regs
                .filter(r => r.scope.endsWith('/static/'))
                .forEach(r => r.unregister()));
        });
    }

    if (isStandalone) return;

    window.addEventListener('beforeinstallprompt', function (event) {
        event.preventDefault();            // своё окно покажем по нажатию кнопки
        deferredPrompt = event;
        showButtons(true);
    });

    window.addEventListener('appinstalled', function () {
        deferredPrompt = null;
        showButtons(false);
    });

    document.addEventListener('DOMContentLoaded', function () {
        if (isIos || isShortcutOnlyBrowser) showButtons(true);
    });

    document.addEventListener('click', function (event) {
        if (!event.target.closest('[data-install]')) return;
        if (deferredPrompt) {
            deferredPrompt.prompt();
            deferredPrompt.userChoice.finally(() => { deferredPrompt = null; showButtons(false); });
        } else if (isIos || isShortcutOnlyBrowser) {
            const modal = document.getElementById(isIos ? 'installIosModal' : 'installAndroidModal');
            if (modal && window.bootstrap) bootstrap.Modal.getOrCreateInstance(modal).show();
        }
    });
})();
