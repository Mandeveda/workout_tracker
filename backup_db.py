"""Резервная копия базы сайта в файл SQLite (без mysqldump — его на хостинге может не быть).

    python backup_db.py                     # копия в ~/backups/tracker-YYYY-MM-DD_HHMM.db
    python backup_db.py --keep 30           # хранить 30 последних копий (по умолчанию 14)

Копируются все таблицы, каждая строка сверяется с базой; в файл записывается и ревизия
миграций. Восстановление — в пустую базу MySQL, в которой таблицы созданы миграциями:
    DATABASE_URL="mysql://…" flask --app passenger_wsgi:application db upgrade
    python transfer_to_mysql.py --from sqlite:////путь/к/копии.db --to "mysql://…" --apply
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, text

from config import Config, database_settings
from app import models   # импорт моделей регистрирует все таблицы в db.metadata
from transfer_to_mysql import copy_and_verify, fail, revision


def main():
    parser = argparse.ArgumentParser(description='Резервная копия базы в файл SQLite')
    parser.add_argument('--out', default=str(Path.home() / 'backups'), help='папка для копий (по умолчанию ~/backups)')
    parser.add_argument('--keep', type=int, default=14, help='сколько последних копий хранить')
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)                                   # в копии — почта и хэши паролей
    path = out / f"tracker-{datetime.now():%Y-%m-%d_%H%M}.db"
    if path.exists():
        fail(f'{path} уже есть — подождите минуту')

    source_url, options = database_settings(Config.SQLALCHEMY_DATABASE_URI)
    source = create_engine(source_url, **options)
    target = create_engine(f'sqlite:///{path}')
    tables = models.db.metadata.sorted_tables

    try:
        with source.connect() as src, target.begin() as dst:
            rev = revision(src)
            if not rev:
                fail('в базе нет ревизии миграций (alembic_version)')
            models.db.metadata.create_all(dst)
            dst.execute(text('CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)'))
            dst.execute(text('INSERT INTO alembic_version VALUES (:rev)'), {'rev': rev})
            report = copy_and_verify(src, dst, tables)
    except BaseException:
        path.unlink(missing_ok=True)                   # недоделанную копию не оставляем
        raise
    path.chmod(0o600)

    rows = sum(count for _, count in report)
    print(f'Копия: {path} ({path.stat().st_size // 1024} КБ), {rows} строк, ревизия {rev} — все строки совпадают.')

    old = sorted(out.glob('tracker-*.db'))[:-args.keep] if args.keep > 0 else []
    for stale in old:
        stale.unlink()
    if old:
        print(f'Удалено старых копий: {len(old)} (хранятся {args.keep} последних).')


if __name__ == '__main__':
    sys.exit(main())
