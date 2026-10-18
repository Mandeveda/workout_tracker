// static/js/perform.js — экран выполнения тренировки (workouts/perform.html)
//
// Подход отмечается кнопкой ✓: пустые поля заполняются плановыми значениями
// (подсказка в placeholder), строка становится «выполненной» и сразу сохраняется.
// На сервер уходят только отмеченные подходы; подход, с которого сняли отметку,
// сервер удаляет (см. workouts.save_progress).
document.addEventListener('DOMContentLoaded', function () {
    const root = document.querySelector('.session');
    if (!root) return;

    const REST_SECONDS = 90;
    const rows = Array.from(root.querySelectorAll('.set-row'));
    const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    const statusEl = document.getElementById('saveStatus');
    let saveTimer = null;
    let dirty = false;

    // ---------- расчёты ----------
    function num(input) {
        if (!input) return 0;
        const value = parseFloat(String(input.value).replace(',', '.'));
        return isNaN(value) ? 0 : value;
    }

    function inputsOf(row) {
        return Array.from(row.querySelectorAll('.cell-in'));
    }

    // Процент выполнения подхода — та же логика, что в SetLog.calculate_completion
    function percentOf(row) {
        const type = row.dataset.type;
        const planA = parseFloat(row.dataset.planA) || 0;   // вес (кг) или минуты
        const planB = parseFloat(row.dataset.planB) || 0;   // повторения или км
        const inputs = inputsOf(row);
        if (type === 'cardio') {
            const minutes = num(inputs[0]);
            return planA > 0 ? Math.min(100, minutes / planA * 100) : 100;
        }
        const reps = num(inputs[inputs.length - 1]);
        if (planB <= 0) return 100;
        if (type === 'strength') {
            const weight = num(inputs[0]);
            if (planA > 0) return Math.min(100, (weight * reps) / (planA * planB) * 100);
        }
        return Math.min(100, reps / planB * 100);
    }

    function paintRow(row) {
        let badge = row.querySelector('.set-pct');
        const done = row.classList.contains('done');
        const pct = done ? Math.round(percentOf(row)) : 100;
        row.classList.toggle('under', done && pct < 100);
        if (done && pct < 100) {
            if (!badge) {
                badge = document.createElement('span');
                badge.className = 'set-pct num';
                row.querySelector('.check').after(badge);
            }
            badge.textContent = pct + '%';
        } else if (badge) {
            badge.remove();
        }
    }

    function updateSummary() {
        const done = rows.filter(r => r.classList.contains('done'));
        const tonnage = done
            .filter(r => r.dataset.type === 'strength')
            .reduce((sum, r) => { const i = inputsOf(r); return sum + num(i[0]) * num(i[1]); }, 0);
        const share = rows.length ? done.length / rows.length * 100 : 0;
        document.getElementById('progressBar').style.width = share + '%';
        document.getElementById('progressText').textContent = `${done.length} из ${rows.length} подходов`;
        document.getElementById('tonnageText').textContent = `Тоннаж ${Math.round(tonnage).toLocaleString('ru-RU')} кг`;
    }

    // ---------- сохранение ----------
    function buildForm() {
        const form = new FormData();
        form.append('csrf_token', csrf);
        rows.filter(r => r.classList.contains('done')).forEach(row => {
            inputsOf(row).forEach(input => form.append(input.name, String(input.value).replace(',', '.')));
        });
        return form;
    }

    function setStatus(text, isError) {
        WorkoutUI.setStatus(statusEl, text, isError);
    }

    function save() {
        clearTimeout(saveTimer);
        dirty = false;
        setStatus('Сохранение…');
        return fetch(root.dataset.saveUrl, { method: 'POST', body: buildForm() })
            .then(response => response.json().then(data => ({ ok: response.ok, data })))
            .then(({ ok, data }) => {
                if (!ok || !data.success) throw new Error(data.error || 'save failed');
                setStatus(WorkoutUI.savedAt());
            })
            .catch(error => {
                dirty = true;
                setStatus('Не сохранено — проверьте интернет, повторим при следующем действии', true);
                throw error;
            });
    }

    function saveSoon() {
        dirty = true;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => save().catch(() => {}), 800);
    }

    // При закрытии страницы отправляем несохранённое без ожидания ответа
    window.addEventListener('pagehide', function () {
        if (dirty && navigator.sendBeacon) navigator.sendBeacon(root.dataset.saveUrl, buildForm());
    });

    // ---------- отметка подхода ----------
    root.addEventListener('click', function (event) {
        const check = event.target.closest('.check');
        if (!check) return;
        const row = check.closest('.set-row');
        if (row.classList.contains('done')) {
            row.classList.remove('done');
        } else {
            inputsOf(row).forEach(input => { if (input.value.trim() === '') input.value = input.placeholder; });
            row.classList.add('done');
            rest.start(REST_SECONDS);
        }
        paintRow(row);
        updateSummary();
        save().catch(() => {});
    });

    root.addEventListener('input', function (event) {
        const row = event.target.closest('.set-row');
        if (!row) return;
        paintRow(row);
        updateSummary();
        if (row.classList.contains('done')) saveSoon();
    });

    // ---------- завершение ----------
    function finish() {
        const done = rows.filter(r => r.classList.contains('done')).length;
        const question = done < rows.length
            ? `Отмечено ${done} из ${rows.length} подходов. Завершить тренировку? Изменить результаты после этого будет нельзя.`
            : 'Завершить тренировку? Изменить результаты после этого будет нельзя.';
        if (!confirm(question)) return;
        save()
            .then(() => fetch(root.dataset.completeUrl, { method: 'POST', headers: { 'X-CSRFToken': csrf } }))
            .then(response => response.json())
            .then(data => {
                if (!data.success) throw new Error(data.error);
                window.location.href = data.redirect;
            })
            .catch(() => setStatus('Не удалось завершить тренировку — проверьте интернет и нажмите ещё раз', true));
    }
    document.getElementById('finishBtn').addEventListener('click', finish);
    document.getElementById('finishBtnBottom').addEventListener('click', finish);

    const rest = WorkoutUI.restTimer();

    WorkoutUI.startElapsed(document.getElementById('elapsed'), root.dataset.started);

    rows.forEach(paintRow);
    updateSummary();
});
