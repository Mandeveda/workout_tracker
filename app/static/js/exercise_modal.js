// static/js/exercise_modal.js — окно «Техника выполнения» (разметка в _exercise_modal.html)
(function () {
    const typeNames = { strength: 'Силовое', bodyweight: 'Собственный вес', cardio: 'Кардио' };

    function spinner() {
        return '<div class="text-center py-4"><div class="spinner-border" role="status">' +
               '<span class="visually-hidden">Загрузка...</span></div></div>';
    }

    function render(data) {
        document.getElementById('exerciseModalTitle').textContent = data.name;

        let media = '';
        const imageUrl = safeUrl(data.media_url);
        if ((data.media_type === 'image' || data.media_type === 'gif') && imageUrl) {
            media = `<div class="ex-media"><img src="${escapeHtml(imageUrl)}" alt="${escapeHtml(data.name)}"></div>`;
        } else if (data.media_type === 'youtube' && data.youtube_id) {
            media = `<div class="ex-media"><iframe src="https://www.youtube.com/embed/${encodeURIComponent(data.youtube_id)}"
                        title="${escapeHtml(data.name)}" allowfullscreen
                        allow="accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture"></iframe></div>`;
        }

        const facts = [`<div><span class="label">Тип</span><div>${escapeHtml(typeNames[data.exercise_type] || data.exercise_type)}</div></div>`];
        if (data.muscle_group) {
            const group = data.muscle_group + (data.muscle_subgroup ? ' · ' + data.muscle_subgroup : '');
            facts.push(`<div><span class="label">Мышцы</span><div>${escapeHtml(group)}</div></div>`);
        }
        if (data.last_result) {
            const r = data.last_result;
            const value = (r.weight ? escapeHtml(r.weight) + ' кг × ' : '') + escapeHtml(r.reps);
            facts.push(`<div><span class="label">Последний результат</span><div class="num">${value} · ${escapeHtml(r.date)}</div></div>`);
        }

        document.getElementById('exerciseModalContent').innerHTML = `
            ${media}
            <div class="ex-facts">${facts.join('')}</div>
            <span class="label">Техника</span>
            <p class="ex-description">${escapeHtml(data.description || 'Описание пока не добавлено.')}</p>`;
    }

    function open(exerciseId) {
        const content = document.getElementById('exerciseModalContent');
        document.getElementById('exerciseModalTitle').textContent = 'Техника выполнения';
        content.innerHTML = spinner();
        bootstrap.Modal.getOrCreateInstance(document.getElementById('exerciseModal')).show();

        fetch(`/exercises/get_exercise_data/${encodeURIComponent(exerciseId)}`)
            .then(response => {
                if (!response.ok) throw new Error(response.status);
                return response.json();
            })
            .then(render)
            .catch(() => {
                content.innerHTML = '<div class="alert alert-danger mb-0">Не удалось загрузить упражнение. Проверьте соединение и попробуйте ещё раз.</div>';
            });
    }

    document.addEventListener('click', function (event) {
        const link = event.target.closest('.exercise-name-link[data-exercise-id]');
        if (!link) return;
        event.preventDefault();
        open(link.dataset.exerciseId);
    });
})();
