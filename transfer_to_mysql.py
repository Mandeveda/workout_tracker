"""Перенос данных из SQLite в MySQL (ROADMAP C.3).

    python transfer_to_mysql.py --to "mysql://пользователь:пароль@localhost/база"           # репетиция
    python transfer_to_mysql.py --to "mysql://пользователь:пароль@localhost/база" --apply   # перенос

Перед запуском в MySQL должны быть созданы таблицы миграциями (пустые):
    DATABASE_URL="mysql://…" flask --app passenger_wsgi:application db upgrade

Что делает:
1. проверяет, что обе базы на одной ревизии миграций и что в MySQL ещё нет данных;
2. ищет в SQLite то, что MySQL не примет: «висячие» ссылки (SQLite их не проверяет),
   пустые обязательные поля и строки длиннее поля;
3. в одной транзакции копирует все таблицы с сохранением id, сверяет каждую строку
   и количество записей; без --apply — откатывает (репетиция), с --apply — сохраняет.
Исходная база SQLite не меняется.
"""
import argparse
import math
import sys
from datetime import datetime

from sqlalchemy import create_engine, func, inspect, select, text

from config import BASE_DIR, database_settings
from app import models   # импорт моделей регистрирует все таблицы в db.metadata

BATCH = 500


def fail(message):
    print(f'ОШИБКА: {message}')
    sys.exit(1)


def revision(conn):
    try:
        return conn.execute(text('SELECT version_num FROM alembic_version')).scalar()
    except Exception:
        return None


def same(a, b):
    """Значения равны с учётом того, как их хранит MySQL"""
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)
    if isinstance(a, datetime) and isinstance(b, datetime):
        return abs((a - b).total_seconds()) <= 1      # DATETIME в MySQL — с точностью до секунды
    if isinstance(a, bool) or isinstance(b, bool):
        return (None if a is None else bool(a)) == (None if b is None else bool(b))
    return a == b


def problems_in_source(src, tables):
    found = []
    for table in tables:
        for fk in table.foreign_keys:
            parent = fk.column.table
            column = fk.parent
            orphans = src.execute(
                select(func.count()).select_from(table).where(
                    column.isnot(None),
                    ~column.in_(select(fk.column).select_from(parent)))
            ).scalar()
            if orphans:
                found.append(f'{table.name}.{column.name}: {orphans} строк ссылаются на несуществующие {parent.name}')
        for column in table.columns:
            if not column.nullable and not column.primary_key:
                empty = src.execute(select(func.count()).select_from(table).where(column.is_(None))).scalar()
                if empty:
                    found.append(f'{table.name}.{column.name}: {empty} строк без значения в обязательном поле')
            length = getattr(column.type, 'length', None)
            if length:
                too_long = src.execute(select(func.count()).select_from(table)
                                       .where(func.length(column) > length)).scalar()
                if too_long:
                    found.append(f'{table.name}.{column.name}: {too_long} строк длиннее {length} символов')
    return found


def copy_and_verify(src, dst, tables):
    report = []
    for table in tables:
        rows = [dict(r) for r in src.execute(select(table)).mappings()]
        for start in range(0, len(rows), BATCH):
            dst.execute(table.insert(), rows[start:start + BATCH])
        pk = list(table.primary_key.columns)
        copied = {tuple(r[c.name] for c in pk): r for r in dst.execute(select(table)).mappings()}
        if len(copied) != len(rows):
            fail(f'{table.name}: в SQLite {len(rows)} строк, в MySQL {len(copied)}')
        for row in rows:
            other = copied.get(tuple(row[c.name] for c in pk))
            if other is None:
                fail(f'{table.name}: строка {row} не найдена после копирования')
            for name, value in row.items():
                if not same(value, other[name]):
                    fail(f'{table.name} id={row.get("id")}: {name} было {value!r}, стало {other[name]!r}')
        report.append((table.name, len(rows)))
    return report


def main():
    parser = argparse.ArgumentParser(description='Перенос данных SQLite → MySQL')
    parser.add_argument('--from', dest='source', default=f"sqlite:///{BASE_DIR / 'instance' / 'workout.db'}",
                        help='исходная база (по умолчанию instance/workout.db)')
    parser.add_argument('--to', dest='target', required=True, help='mysql://пользователь:пароль@localhost/база')
    parser.add_argument('--apply', action='store_true', help='сохранить (без него — репетиция с откатом)')
    args = parser.parse_args()

    target_url, options = database_settings(args.target)
    source = create_engine(args.source)
    target = create_engine(target_url, **options)
    tables = models.db.metadata.sorted_tables           # родительские таблицы раньше зависимых

    with source.connect() as src, target.connect() as dst:
        src_rev, dst_rev = revision(src), revision(dst)
        if not src_rev or src_rev != dst_rev:
            fail(f'ревизии миграций не совпадают: SQLite {src_rev}, MySQL {dst_rev}. '
                 f'Сначала flask db upgrade на обеих базах.')
        missing = set(t.name for t in tables) - set(inspect(dst).get_table_names())
        if missing:
            fail(f'в MySQL нет таблиц: {", ".join(sorted(missing))}')
        filled = [t.name for t in tables if dst.execute(select(func.count()).select_from(t)).scalar()]
        if filled:
            fail(f'в MySQL уже есть данные ({", ".join(filled)}) — перенос только в пустую базу')
        if dst.dialect.name in ('mysql', 'mariadb'):
            charset = dst.execute(text('SELECT @@character_set_database, @@collation_database')).one()
            print(f'MySQL: кодировка {charset[0]}, сравнение {charset[1]}')
            if charset[0] != 'utf8mb4':
                fail('база MySQL не в utf8mb4 — таблицы создавались не миграциями проекта?')

        found = problems_in_source(src, tables)
        if found:
            print('В SQLite есть данные, которые MySQL не примет:')
            for line in found:
                print('  -', line)
            fail('исправьте их и запустите снова')

        dst.rollback()                   # закрыть транзакцию, которую открыли проверки выше
        transaction = dst.begin()
        try:
            report = copy_and_verify(src, dst, tables)
        except Exception as error:
            transaction.rollback()
            fail(f'{type(error).__name__}: {error}')
        for name, count in report:
            print(f'  {name:<24} {count:>6}  ✓')
        if args.apply:
            transaction.commit()
            print(f'Готово: перенесено {sum(c for _, c in report)} строк, все совпадают.')
        else:
            transaction.rollback()
            print('Репетиция прошла: все строки совпадают. Изменения отменены. Для переноса добавьте --apply.')


if __name__ == '__main__':
    main()
