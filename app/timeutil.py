"""Время и даты.

В базе время хранится в UTC без часового пояса (datetime.utcnow()). Всё, что связано
с «сегодня» и днями — расписание, неделя, календарь, — считается по местному времени
сайта: настройка APP_TIMEZONE (по умолчанию Europe/Moscow).
"""
from datetime import datetime, time, timedelta, timezone

from flask import current_app

MOSCOW = timezone(timedelta(hours=3))   # запасной вариант, если в системе нет базы часовых поясов


def _site_tz():
    name = current_app.config.get('APP_TIMEZONE', 'Europe/Moscow')
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:
        return MOSCOW


def utcnow():
    """Текущее время UTC в формате базы (без часового пояса). Отдельная функция — чтобы подменять в тестах"""
    return datetime.utcnow()


def to_local(dt):
    """UTC из базы → местное время сайта (без часового пояса)"""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(_site_tz()).replace(tzinfo=None)


def local_now():
    return to_local(utcnow())


def local_today():
    return local_now().date()


def local_date(dt):
    """Местная дата момента, сохранённого в UTC"""
    return to_local(dt).date()


def utc_start_of(day):
    """Начало местного дня day (00:00) в UTC — граница для запросов к базе"""
    local_midnight = datetime.combine(day, time.min).replace(tzinfo=_site_tz())
    return local_midnight.astimezone(timezone.utc).replace(tzinfo=None)
