// static/js/free_workout.js — свободная тренировка (workouts/free_workout.html)
//
// Карточки упражнений строятся из JSON (#freeWorkoutData). Подход отмечается ✓ и сразу
// сохраняется; сервер получает все отмеченные подходы целиком и перезаписывает их
// (см. workouts.free_workout). Неотмеченные строки не сохраняются.
document.addEventListener('DOMContentLoaded', function () {
    const root = document.getElementById('freeSession');
    if (!root) return;

    const REST_SECONDS = 90;
    const data = JSON.parse(document.getElementById('freeWorkoutData').textContent);
    const catalog = data.catalog;
    const list = document.getElementById('exercises');
    const statusEl = document.getElementById('saveStatus');
    const csrf = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    const rest = WorkoutUI.restTimer();
    const typeNames = { strength: 'Силовое', bodyweight: 'Собственный вес', cardio: 'Кардио' };
    let saveUrl = root.dataset.saveUrl;
    let saveTimer = null;
    let dirty = false;

    // ---------- поля подхода в зависимости от типа ----------
    // Для кардио: минуты хранятся в reps, километры — в weight (как в SetLog)
    function fieldsFor(type) {
        if (type === 'cardio') return [{ key: 'r', label: 'мин', mode: 'numeric' }, { key: 'w', label: 'км', mode: 'decimal' }];
        if (type === 'bodyweight') return [{ key: 'r', label: 'повт', mode: 'numeric' }];
        return [{ key: 'w', label: 'кг', mode: 'decimal' }, { key: 'r', label: 'повт', mode: 'numeric' }];
    }

    function fmt(value) {
        if (value === null || value === undefined || value === '') return '';
        const n = Number(value);
        return isNaN(n) ? String(value) : String(Math.round(n * 100) / 100);
    }

    function prevText(type, prev) {
        if (!prev) return '';
        if (type === 'cardio') return `прошлый раз ${fmt(prev.r)} мин${prev.w ? ', ' + fmt(prev.w) + ' км' : ''}`;
        if (type === 'bodyweight') return `прошлый раз ${fmt(prev.r)}`;
        return `прошлый раз ${fmt(prev.w)} кг × ${fmt(prev.r)}`;
    }

    // ---------- карточки ----------
    function createCard(exercise, sets) {
        const card = document.createElement('article');
        card.className = 'ex';
        card.dataset.exerciseId = exercise.id;
        card.dataset.type = exercise.type;
        card._prev = exercise.prev || null;
        const fields = fieldsFor(exercise.type);
        card.innerHTML = `
            <div class="ex-head ex-head-row">
                <div>
                    <button type="button" class="ex-name exercise-name-link" data-exercise-id="${escapeHtml(exercise.id)}">
                        <svg class="icon"><use href="#i-info"/></svg>${escapeHtml(exercise.name)}
                    </button>
                    <div class="ex-type">${escapeHtml(typeNames[exercise.type] || exercise.type)}<span class="ex-prev num"></span></div>
                </div>
                <button type="button" class="ex-remove" aria-label="Убрать упражнение">Убрать</button>
            </div>
            <table class="sets">
                <thead><tr><th>№</th>${fields.map(f => `<th>${f.label}</th>`).join('')}<th><span class="visually-hidden">Отметка</span></th></tr></thead>
                <tbody></tbody>
            </table>
            <button type="button" class="add-set">+ Подход</button>`;
        list.appendChild(card);
        updatePrev(card);
        (sets && sets.length ? sets : [null]).forEach(set => addRow(card, set));
        return card;
    }

    function updatePrev(card) {
        const text = prevText(card.dataset.type, card._prev);
        card.querySelector('.ex-prev').textContent = text ? ' · ' + text : '';
    }

    // Новая строка: сохранённый подход (done) или пустая с подсказками
    function addRow(card, saved) {
        const tbody = card.querySelector('tbody');
        const fields = fieldsFor(card.dataset.type);
        const lastRow = tbody.lastElementChild;
        const hint = {};
        fields.forEach(f => {
            const fromLast = lastRow ? (lastRow.querySelector(`[data-key="${f.key}"]`).value || lastRow.querySelector(`[data-key="${f.key}"]`).placeholder) : '';
            hint[f.key] = fromLast || (card._prev ? fmt(card._prev[f.key]) : '');
        });
        const row = document.createElement('tr');
        row.className = 'set-row' + (saved ? ' done' : '');
        row.innerHTML = `<td><span class="set-n"></span></td>` +
            fields.map(f => `<td><input class="cell-in" type="text" inputmode="${f.mode}" data-key="${f.key}"
                value="${saved ? escapeHtml(fmt(saved[f.key])) : ''}"
                placeholder="${escapeHtml(hint[f.key] || f.label)}" aria-label="${f.label}"></td>`).join('') +
            `<td><button type="button" class="check" aria-label="Подход выполнен"><svg class="icon"><use href="#i-check"/></svg></button></td>`;
        tbody.appendChild(row);
        renumber(card);
        return row;
    }

    function renumber(card) {
        card.querySelectorAll('.set-row').forEach((row, i) => { row.querySelector('.set-n').textContent = i + 1; });
    }

    function value(input) {
        const n = parseFloat(String(input.value).replace(',', '.'));
        return isNaN(n) ? 0 : n;
    }

    function refresh() {
        const cards = Array.from(list.children);
        const doneRows = list.querySelectorAll('.set-row.done');
        let tonnage = 0;
        doneRows.forEach(row => {
            if (row.closest('.ex').dataset.type !== 'strength') return;
            tonnage += value(row.querySelector('[data-key="w"]')) * value(row.querySelector('[data-key="r"]'));
        });
        document.getElementById('emptyState').hidden = cards.length > 0;
        document.getElementById('progressText').textContent = `${doneRows.length} подх. · ${cards.length} упр.`;
        document.getElementById('tonnageText').textContent = `Тоннаж ${Math.round(tonnage).toLocaleString('ru-RU')} кг`;
    }

    // ---------- сохранение ----------
    function buildForm(action) {
        const form = new FormData();
        form.append('csrf_token', csrf);
        form.append('action', action);
        list.querySelectorAll('.ex').forEach(card => {
            let n = 0;
            card.querySelectorAll('.set-row.done').forEach(row => {
                n += 1;
                const w = row.querySelector('[data-key="w"]');
                form.append('exercise_id[]', card.dataset.exerciseId);
                form.append('set_number[]', n);
                form.append('weight[]', w ? String(value(w)) : '0');
                form.append('reps[]', String(Math.round(value(row.querySelector('[data-key="r"]')))));
            });
        });
        return form;
    }

    function save(action) {
        clearTimeout(saveTimer);
        dirty = false;
        WorkoutUI.setStatus(statusEl, 'Сохранение…');
        return fetch(saveUrl, {
            method: 'POST',
            headers: { 'X-Requested-With': 'fetch', 'X-CSRFToken': csrf },
            body: buildForm(action || 'save')
        })
            .then(response => response.json().then(json => ({ ok: response.ok, json })))
            .then(({ ok, json }) => {
                if (!ok || !json.success) throw new Error('save failed');
                saveUrl = root.dataset.saveUrl.split('?')[0] + '?session_id=' + json.session_id;
                WorkoutUI.setStatus(statusEl, WorkoutUI.savedAt());
                return json;
            })
            .catch(error => {
                dirty = true;
                WorkoutUI.setStatus(statusEl, 'Не сохранено — проверьте интернет, повторим при следующем действии', true);
                throw error;
            });
    }

    function saveSoon() {
        dirty = true;
        clearTimeout(saveTimer);
        saveTimer = setTimeout(() => save().catch(() => {}), 800);
    }

    window.addEventListener('pagehide', function () {
        if (dirty && navigator.sendBeacon) navigator.sendBeacon(saveUrl, buildForm('save'));
    });

    // ---------- действия в карточках ----------
    list.addEventListener('click', function (event) {
        const card = event.target.closest('.ex');
        if (!card) return;

        if (event.target.closest('.check')) {
            const row = event.target.closest('.set-row');
            if (row.classList.contains('done')) {
                row.classList.remove('done');
            } else {
                const inputs = row.querySelectorAll('.cell-in');
                inputs.forEach(input => {
                    if (input.value.trim() === '' && !isNaN(parseFloat(input.placeholder))) input.value = input.placeholder;
                });
                const reps = row.querySelector('[data-key="r"]');
                if (value(reps) <= 0) {
                    reps.focus();
                    WorkoutUI.setStatus(statusEl, card.dataset.type === 'cardio' ? 'Укажите минуты' : 'Укажите количество повторений', true);
                    return;
                }
                row.classList.add('done');
                rest.start(REST_SECONDS);
            }
            refresh();
            save().catch(() => {});
            return;
        }

        if (event.target.closest('.add-set')) {
            const row = addRow(card, null);
            row.querySelector('.cell-in').focus();
            return;
        }

        if (event.target.closest('.ex-remove')) {
            const hasDone = card.querySelector('.set-row.done');
            if (hasDone && !confirm('Убрать упражнение вместе с отмеченными подходами?')) return;
            card.remove();
            refresh();
            if (hasDone) save().catch(() => {});
        }
    });

    list.addEventListener('input', function (event) {
        const row = event.target.closest('.set-row');
        if (!row) return;
        refresh();
        if (row.classList.contains('done')) saveSoon();
    });

    // ---------- выбор упражнения ----------
    const pickerEl = document.getElementById('exercisePicker');
    const search = document.getElementById('pickerSearch');
    const pickerList = document.getElementById('pickerList');

    function renderPicker() {
        const q = search.value.trim().toLowerCase();
        const found = catalog.filter(e => !q || e.name.toLowerCase().includes(q) || (e.group || '').toLowerCase().includes(q));
        pickerList.innerHTML = found.length
            ? found.map(e => `<li><button type="button" class="picker-item" data-id="${escapeHtml(e.id)}">
                    <span class="picker-name">${escapeHtml(e.name)}</span>
                    <span class="picker-meta">${escapeHtml(typeNames[e.type] || e.type)}${e.group ? ' · ' + escapeHtml(e.group) : ''}</span>
                </button></li>`).join('')
            : '<li class="picker-empty">Ничего не найдено. Упражнения добавляют эксперты в разделе «Упражнения».</li>';
    }
    search.addEventListener('input', renderPicker);
    pickerEl.addEventListener('shown.bs.modal', function () { search.focus(); });
    pickerEl.addEventListener('show.bs.modal', function () { search.value = ''; renderPicker(); });

    pickerList.addEventListener('click', function (event) {
        const item = event.target.closest('.picker-item');
        if (!item) return;
        const exercise = catalog.find(e => String(e.id) === item.dataset.id);
        bootstrap.Modal.getInstance(pickerEl).hide();

        // Упражнение уже в тренировке — добавляем подход в его карточку
        const existing = list.querySelector(`.ex[data-exercise-id="${CSS.escape(String(exercise.id))}"]`);
        const card = existing || createCard(exercise, []);
        const row = existing ? addRow(card, null) : card.querySelector('.set-row');
        refresh();
        card.scrollIntoView({ behavior: 'smooth', block: 'center' });

        if (!existing) {
            fetch(`/exercises/get_exercise_data/${encodeURIComponent(exercise.id)}`)
                .then(r => r.ok ? r.json() : null)
                .then(info => {
                    if (!info || !info.last_result) return;
                    card._prev = { w: info.last_result.weight || 0, r: info.last_result.reps };
                    updatePrev(card);
                    row.querySelectorAll('.cell-in').forEach(input => {
                        const hint = fmt(card._prev[input.dataset.key]);
                        if (hint && isNaN(parseFloat(input.placeholder))) input.placeholder = hint;
                    });
                })
                .catch(() => {});
        }
    });

    // ---------- завершение ----------
    function finish() {
        const done = list.querySelectorAll('.set-row.done').length;
        if (!done) {
            WorkoutUI.setStatus(statusEl, 'Отметьте хотя бы один подход, чтобы завершить тренировку', true);
            return;
        }
        if (!confirm(`Завершить тренировку? Отмечено подходов: ${done}. Изменить результаты после этого будет нельзя.`)) return;
        save('complete')
            .then(json => { window.location.href = json.redirect; })
            .catch(() => {});
    }
    document.getElementById('finishBtn').addEventListener('click', finish);
    document.getElementById('finishBtnBottom').addEventListener('click', finish);

    // ---------- старт ----------
    WorkoutUI.startElapsed(document.getElementById('elapsed'), root.dataset.started || null);
    data.groups.forEach(group => createCard(group, group.sets));
    refresh();
});
