# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

KettleBell Pro — a Django 5.2 app (Spanish-language UI) for browsing kettlebell exercises and generating/tracking workout routines. Single Django project (`kettelbell/`, note the spelling) with one app (`exercises/`).

## Commands

A Windows virtualenv lives at `venv/`. Activate it or call its Python directly:

```powershell
venv\Scripts\python.exe manage.py runserver        # dev server (SQLite by default)
venv\Scripts\python.exe manage.py migrate
venv\Scripts\python.exe manage.py test exercises   # run app tests
venv\Scripts\python.exe manage.py test exercises.tests.AuthTests.test_login_user  # single test
venv\Scripts\python.exe populate_exercises.py      # seed the exercise catalog
venv\Scripts\python.exe test_routine_generator.py  # standalone smoke test for RoutineGenerator (not a Django TestCase; writes to the active DB)
```

Docker stack (Django+Gunicorn, PostgreSQL, Adminer):

```
docker compose up --build
# App: http://localhost:8000 | Adminer: http://localhost:8081 | Postgres: localhost:5433 (user/pass/db: kettlebell)
```

`docker/entrypoint.sh` waits for Postgres, then runs `migrate` and `collectstatic` automatically on container start.

## Database switching

`kettelbell/settings.py` picks the database from the environment: if `POSTGRES_DB` is set it uses PostgreSQL, otherwise it falls back to the local `db.sqlite3`. Docker sets the Postgres vars; local dev without env vars uses SQLite. Same pattern for `DJANGO_DEBUG` (defaults to True locally, False in compose) and `DJANGO_ALLOWED_HOSTS`. WhiteNoise middleware/storage is only enabled if the package is installed (`find_spec` check).

## Architecture

All domain logic lives in the `exercises` app:

- **Models** (`exercises/models.py`): `Exercise` (rich text fields: instructions, setup_tips, common_mistakes, progressions, precautions, muscles_targeted, variations — each stored as newline-separated text), `Workout` + `WorkoutExercise` (ordered through-model with sets/reps/notes), `Favorite`, `WorkoutLog`. `Exercise` and `Workout` auto-generate unique slugs in `save()` via `build_unique_slug`; URLs are slug-based. `Workout.created_by` drives visibility: views only expose public workouts plus the requesting user's own (see `get_visible_workouts` in views.py).
- **Routine generation** (`exercises/utils.py`): `RoutineGenerator` builds a `Workout` from duration/difficulty/focus — warmup (beginner flexibility/cardio) → main block (~4 min per exercise, focus category, falls back to `full_body` if too few match) → cooldown (flexibility). Sets/reps/notes are assigned per phase and category. Generated workouts are `is_public=False`.
- **Views** (`exercises/views.py`): function-based. Category/difficulty listing pages share the `taxonomy_overview.html` and `exercise_collection.html` templates, parameterized via context (`page_title`, `cards`, `url_name`, etc.). `exercise_detail` splits the Exercise text fields into line lists and builds `coaching_cards` with fallback copy. Two JSON POST endpoints (`api/toggle-favorite/`, `api/log-workout/`) read `request.body` as JSON.
- **Category/difficulty values** are fixed choice lists on `Exercise` (`strength`, `cardio`, `flexibility`, `full_body` / `beginner`, `intermediate`, `advanced`) with Spanish display labels; views validate URL params against these dicts.
- **Templates/static** are app-local (`exercises/templates/`, `exercises/static/exercises/`); all pages extend `base.html`.
- **Styling is custom CSS only** (`static/exercises/css/styles.css` + per-template `<style>` blocks). The Tailwind Play CDN and DaisyUI were intentionally removed for page-weight reasons — do NOT add Tailwind/DaisyUI utility classes to templates expecting them to work; extend `styles.css` or use the existing custom classes (`btn`, `form-control`, `card-*`, etc.) instead. Auth form inputs get `class="form-control"` from `forms.py`.
- **Landing page is a light preview**: `landing_page` serves only `FEATURED_EXERCISES_LIMIT` (8) exercises plus `total_exercises`, not the whole catalog; the full browsable list with search/pagination lives at `exercise_list` (`/exercises/`).
- **Exercise images are static assets, not media**: files live in `exercises/static/exercises/img/catalog/` and `Exercise.image` is a `CharField` holding just the filename (e.g. `kettlebell_swing.jpg`); templates use the `Exercise.image_url` property, which resolves through staticfiles (WhiteNoise serves them in production — there is no `/media/` route or `MEDIA_ROOT` anymore). Filenames are derived from the exercise name lowercased with spaces→underscores and `:`/`,` stripped. All images share a 3-panel start/middle/end sequence style — keep new ones consistent. Note: `kettlebell_clean.jpg` is a copy of the clean-and-press image because no dedicated clean illustration was ever generated.

## Notes

- UI text, model verbose_names, and seed data are in Spanish; keep new user-facing strings in Spanish. `fix_exercise_text_encoding.py` exists because of past mojibake issues (UTF-8 read as latin-1) in exercise text — beware of encoding when writing seed data on Windows.
- `populate_exercises.py` is the source of the exercise catalog (~50 exercises with full coaching text).
