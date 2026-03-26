# Copilot Instructions — SIG Intranet (Panel SIG)

## Architecture Overview

Django 4.2 intranet app that serves Power BI dashboards via iframes with per-user access control. Single Django app (`panel`) handles everything. Runs on Windows with Waitress as the WSGI server, installable as a Windows service via NSSM.

**Data flow:** User → Django auth → `PerfilUsuario` M2M lookup → filtered `Panel` list → iframe renders Power BI URL. Staff users can trigger external script execution via a secure backend proxy (`views.actualizar_paneles_view`) that hides the API token from the browser; the frontend polls `/api/estado-job/<job_id>/` every 2s for async job status.

## Project Layout

- `sig_intranet/sig_intranet/` — Django project settings, root URL config
- `sig_intranet/panel/` — The only app: models, views, admin, signals, static assets
- `sig_intranet/templates/panel/` — Django templates (project-level `templates/` dir, not app-level)
- `sig_intranet/.env` — Secrets (`SECRET_KEY`, `API_BASE_TOKEN`, `API_BASE_URL`); hand-parsed in `settings.py` without python-dotenv

## Key Conventions

- **Language:** All model names, comments, UI text, and variable names are in **Spanish** (e.g., `PerfilUsuario`, `paneles`, `nombre`, `activo`). Follow this convention.
- **No third-party deps beyond Django + Waitress.** The `.env` file is parsed manually in `settings.py` (lines 17-24). HTTP calls use `urllib.request`, not `requests`. Keep the dependency footprint minimal.
- **Auth pattern:** Every view uses `@login_required`. Staff-only features are gated with `{% if user.is_staff %}` in templates. Panel access is validated in views via `perfil.paneles.filter(pk=panel.pk).exists()`.
- **Signal auto-creation:** `PerfilUsuario` is auto-created on `User` post_save (see `panel/signals.py`, wired in `panel/apps.py:ready()`).
- **Admin customization:** `User` admin is re-registered with `PerfilUsuarioInline` so panel assignments are managed inline within the user form (`panel/admin.py`).

## External API Proxy Pattern

Views act as a **secure proxy** to `API_BASE_URL` (configured in `.env`). The JWT token is never sent to the browser. Two endpoints:
- `POST /api/actualizar-paneles/` → proxies to `{API_BASE_URL}/ejecutar-script`
- `GET /api/estado-job/<job_id>/` → proxies to `{API_BASE_URL}/estado-job/{job_id}`

When adding new API proxy endpoints, follow the same error-handling structure in `views.py`: catch `HTTPError`, `URLError`, and generic `Exception` separately, returning `JsonResponse` with `success` boolean.

## Frontend

Vanilla JavaScript (`panel/static/js/app.js`) — no frameworks, no build step. Config is passed from Django templates via `data-*` attributes on the `<script>` tag (see `panel.html` bottom). CSS is in `panel/static/css/styles.css` (single file, ~426 lines). After changing static files, run `python manage.py collectstatic`.

## Development Workflow

```bash
cd sig_intranet
python -m venv venv && venv\Scripts\activate
pip install -r requirements.txt    # Django>=4.2,<5.0 + waitress
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver          # dev: http://127.0.0.1:8000
```

Production (Windows intranet): `waitress-serve --listen=0.0.0.0:8000 --threads=4 sig_intranet.wsgi:application`  
Windows service install: run `instalar_servicio.bat` as Administrator (uses NSSM).

## Important Details

- `DEBUG = False` always — static files are served via a `django.views.static.serve` fallback in `sig_intranet/urls.py` (acceptable for intranet, not for internet-facing).
- Database is **SQLite** (`db.sqlite3`). No migrations beyond `0001_initial.py` exist yet.
- Templates use `{% load static %}` and `{% url 'name' %}` — URL names are defined in `panel/urls.py`.
- `LANGUAGE_CODE = 'es-es'`, `TIME_ZONE = 'America/Lima'`.
