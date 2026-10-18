"""Процент выполнения подхода — SetLog.calculate_completion (план 1.2)"""
import pytest
from app import db
from app.models import SetLog


@pytest.mark.parametrize('ex_type, planned, actual, user_weight, expected', [
    ('strength',   (10, 50), (10, 50), None, 100),
    ('strength',   (10, 50), (10, 40), None, 80),
    ('strength',   (10, 50), (12, 60), None, 100),   # перевыполнение ограничено 100%
    ('strength',   (10, 0),  (8, 0),   None, 80),    # план без веса — по повторениям
    ('strength',   (10, 50), (None, None), None, 0),
    ('bodyweight', (10, 0),  (10, 0),  80,   100),
    ('bodyweight', (10, 0),  (5, 0),   80,   50),
    ('cardio',     (30, 0),  (30, 0),  None, 100),   # кардио без дистанции
    ('cardio',     (30, 5),  (15, 2),  None, 50),    # считается по минутам
])
def test_completion_for_new_set(make_exercise, ex_type, planned, actual, user_weight, expected):
    """У только что созданного подхода связь exercise ещё пустая — тип должен браться по exercise_id"""
    exercise = make_exercise('Упражнение', ex_type)
    log = SetLog(session_id=1, exercise_id=exercise.id, set_number=1,
                 planned_reps=planned[0], planned_weight=planned[1],
                 actual_reps=actual[0], actual_weight=actual[1])
    assert log.exercise is None
    assert round(log.calculate_completion(user_weight)) == expected
