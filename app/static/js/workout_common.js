// static/js/workout_common.js — общее для экранов тренировки (perform.js, free_workout.js):
// секундомер, таймер отдыха и строка состояния сохранения.
window.WorkoutUI = (function () {
    function fmtTime(seconds) {
        return Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
    }

    // Секундомер с момента начала тренировки (ISO-строка в UTC или null — «с открытия страницы»)
    function startElapsed(el, startedIso) {
        const started = startedIso ? new Date(startedIso).getTime() : Date.now();
        function tick() {
            const total = Math.max(0, Math.floor((Date.now() - started) / 1000));
            const parts = [Math.floor(total / 3600), Math.floor(total % 3600 / 60), total % 60];
            el.textContent = parts.map(v => String(v).padStart(2, '0')).join(':');
        }
        tick();
        setInterval(tick, 1000);
    }

    // Таймер отдыха в нижней панели (#restBar с #restTime, кнопками [data-rest] и #restSkip)
    function restTimer() {
        const bar = document.getElementById('restBar');
        const time = document.getElementById('restTime');
        let left = 0;
        let interval = null;

        function stop() {
            clearInterval(interval);
            bar.hidden = true;
        }
        function start(seconds) {
            left = seconds;
            time.textContent = fmtTime(left);
            bar.hidden = false;
            clearInterval(interval);
            interval = setInterval(function () {
                left -= 1;
                time.textContent = fmtTime(Math.max(left, 0));
                if (left <= 0) {
                    stop();
                    if (navigator.vibrate) navigator.vibrate(300);
                }
            }, 1000);
        }
        bar.addEventListener('click', function (event) {
            const step = event.target.closest('[data-rest]');
            if (step) {
                left = Math.max(5, left + parseInt(step.dataset.rest, 10));
                time.textContent = fmtTime(left);
            }
            if (event.target.closest('#restSkip')) stop();
        });
        return { start, stop };
    }

    function setStatus(el, text, isError) {
        el.textContent = text;
        el.classList.toggle('is-error', !!isError);
    }

    function savedAt() {
        return 'Сохранено в ' + new Date().toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' });
    }

    return { fmtTime, startElapsed, restTimer, setStatus, savedAt };
})();
