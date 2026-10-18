# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Non-commercial hobby project for athletes (only voluntary donations are planned): avoid sales/SaaS wording in UI copy ("бесплатно", "премиум", pricing).

Workout Tracker — a server-rendered Flask 3 app (Jinja2 + Bootstrap 5 and Chart.js from jsDelivr CDN) for planning and logging strength/cardio workouts. UI text, flash messages, comments and commit messages are in Russian. Deployed to shared hosting via Phusion Passenger (tracker-workout.ru).

## Fix plan

`PLAN.md` tracks the agreed bug-fix plan. When a plan item is completed, mark it `[x]` and append the commit hash in the same change set. Follow the order stated at the top of the file.

## Commands

```bash
source venv/bin/activate
pip install -r requirements.txt

python run.py                 # dev server on 0.0.0.0:5000
python create_db.py           # db.create_all() for a fresh DB
python init_database.py       # seed roles, muscle groups/subgroups, admin user from data_for_init.json
                              # (gitignored, contains a real password; copy data_for_init.example.json to create it)

python recalc_stats.py [--apply]  # recompute SetLog/WorkoutSession completion from stored data
                                  # (dry run by default; rerun after changing calculation logic)

flask --app run db migrate -m "..."   # Alembic via Flask-Migrate
flask --app run db upgrade
```

There are no tests, linter or build step.

## Configuration

- `config.py` loads `.env` from the project root and **raises at import if `SECRET_KEY` is missing**.
- `DATABASE_URL` → otherwise SQLite at `instance/workout.db`. `REDIS_URL`/`RATELIMIT_STORAGE_URI` → limiter storage (default `memory://`). Mail defaults to Yandex SMTP over SSL (used for password reset).
- `create_app()` picks the config class via `get_config()` from `ENVIRONMENT` (`development` → `DevelopmentConfig`: DEBUG, insecure cookies by default; `production` → `ProductionConfig`: `SameSite=Strict`). `SESSION_COOKIE_SECURE` from `.env` overrides the per-environment default (`env_bool` helper).
- `RATELIMIT_DEFAULT_LIMITS` in `config.py` is **not** a Flask-Limiter key (the real one is `RATELIMIT_DEFAULT`), so there is effectively no global limit — only the explicit `@limiter.limit` on auth routes. Renaming it would enable 20 req/hour site-wide. Workout AJAX endpoints (`save_progress`, `complete`) are `@limiter.exempt`.
- The strict CSP header is only added when `ENVIRONMENT=production`; any new external asset host must be added there.

## Architecture

- `app/__init__.py` — app factory; extensions (`db`, `migrate`, `login_manager`, `limiter`, `csrf`, `mail`) are module-level singletons imported elsewhere as `from app import db`. Each file in `app/routes/` defines a `bp` Blueprint that must be registered in `create_app`.
- `app/models.py` — all models; `app/forms.py` — all WTForms.

### Domain model and workout flow

```
Exercise (global catalog, by MuscleGroup/MuscleSubgroup, type: strength|cardio|bodyweight)
WorkoutTemplate (per user) ──< TemplateExercise (planned sets/reps/weight or duration/distance)
WorkoutTemplate ──< WorkoutSchedule (concrete date, status planned/completed/skipped/postponed, planned_data JSON)
WorkoutSchedule ──1 WorkoutSession ──< SetLog (planned vs actual per set)
```

1. `templates` blueprint: user builds a template from catalog exercises (`add_exercise` page).
2. `program` blueprint: two-step wizard (weekdays/period → per-exercise parameters) that generates `WorkoutSchedule` rows; intermediate state lives in `flask.session['program_data']`.
3. `workouts` blueprint: `start` creates a `WorkoutSession` for a schedule, `perform` renders it, `save_progress` / `complete` are JSON endpoints called via `fetch` from `perform.html`. `free_workout` is a session with no template/schedule (`template_id`/`schedule_id` nullable); it reuses any unfinished session (`is_completed=False`).
4. `SetLog.calculate_completion()` computes per-set completion by tonnage (bodyweight uses the user's body weight, cardio compares duration stored in `planned_reps`/`actual_reps`); session `completion_percent`/`total_tonnage` aggregate these. `analytics` (dashboard, calendar, progress, records) reads from these fields.
5. `profile` stores anthropometrics on `User` plus `measurements_history` JSON; BMI / body fat (US Navy) / FFMI are `User` properties.

### Roles and access control

Roles seeded with fixed ids: 1 `admin`, 2 `user` (default `role_id`), 3 `expert` (may add exercises). There is no decorator — checks are inline: `is_admin()` in `routes/admin.py`, `is_expert()` in `routes/exercises.py`, `current_user.can_edit()/can_delete()` (admin or owner via `user_id`/`created_by_id`), and manual `obj.user_id != current_user.id` checks in template/program/workout routes. New routes touching user-owned objects need the same ownership check.

### CSRF

CSRFProtect is global. `base.html` exposes the token in `<meta name="csrf-token">`; `static/js/csrf.js` injects it into every form, and an inline script in `base.html` monkey-patches `window.fetch` to add `X-CSRFToken`. JSON endpoints therefore work without extra code as long as the page extends `base.html`.

### Theme and layout

Bootstrap 5.3 (CDN) recoloured via its `--bs-*` variables in `static/styles.css`; all colours are tokens (`--bg`, `--surface`, `--gold`, …) defined for `:root[data-bs-theme="dark"]` (default) and `[data-bs-theme="light"]`. The theme attribute is set by an inline script in `base.html` `<head>` from `localStorage['tw-theme']` and toggled by `.js-theme-toggle` (utils.js). Fonts: Montserrat (headings, buttons) + Open Sans (body) from Google Fonts — allowed in the production CSP in `config.py`. Use tokens, never literal colours. Layout: sidebar (desktop) / mobile bar + offcanvas + bottom tabbar, in `base.html`. Partials: `_macros.html` (`post_button`, `form_field`), `_icons.html` (SVG sprite, `<use href="#i-name">`), `_flashes.html`. Jinja filters (`app/__init__.py`): `num` (thousands separator, `|num(1)` for decimals) and `plural` (`n|plural('упражнение', 'упражнения', 'упражнений')`). Shared page blocks in styles.css: `.page-head`, `.hero`, `.stats-strip`, `.panel`, `.history-list`, `.pill`; workout screen: `.session-*`, `.ex`, `.sets`, `.set-row`, `.rest-bar`. Legacy coloured `card-header bg-*` classes are neutralised in CSS until each page is redesigned (PLAN.md 6.4). Approved mockup: https://claude.ai/artifact/E74eUQcBUutNVaqtdybAj2

### PWA

`static/manifest.json`, `static/sw.js` (registered from `base.html` as `/static/sw.js`), `main.offline` route + `offline.html`. Bump the cache names in `sw.js` when changing cached static files.

## Database / migrations

`migrations/` contains only a single Alembic revision (`add_is_completed_to_workout_sessions`, `down_revision = None`) — the base schema came from `db.create_all()`, not migrations. Check that the generated migration against an existing DB is sane before applying. Production DB is SQLite at the path hardcoded in `passenger_wsgi.py`.

## Deployment

`.htaccess` + `passenger_wsgi.py` (exposes `application`) with hardcoded server paths (`/home/k/kandybd9/tracker-workout.ru`, venv `venv_tw`, Python 3.10). Local venv is Python 3.12, so avoid 3.11+-only syntax/stdlib features.
