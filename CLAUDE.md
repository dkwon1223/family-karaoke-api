# Family Karaoke 노래방 — Backend API

Django REST API for a Korean-style karaoke bar in Aurora, CO.
Handles reservations, waitlist, menu content, and Stripe payments.

## Stack
- Python / Django + Django REST Framework
- PostgreSQL (hosted on Sevalla)
- djangorestframework-simplejwt (JWT auth)
- stripe-python for payments
- django-environ for env vars
- pytest + pytest-django for tests
- django-q2 for scheduled tasks (ORM-backed, no Redis required)

## Project Structure
```
family_karaoke_api/   # Django project settings
reservations/         # Booking, conflict detection, state machine
waitlist/             # Ephemeral walk-in queue, SMS notifications
rooms/                # RoomProfile — capacity, rate, amenities
menu/                 # MenuItem, BusinessInfo (singleton), CMS data
accounts/             # Custom user model, auth endpoints
payments/             # Stripe PaymentIntent, webhook ingestion, refunds
core/                 # TimeStampedModel, shared utils, middleware
```

## Settings
- Settings are split across `config/settings/base.py`, `local.py`, and `production.py`
- Local dev defaults to `config.settings.local` via `os.environ.setdefault` in `manage.py`, `wsgi.py`, and `asgi.py`
- Sevalla overrides this by injecting `DJANGO_SETTINGS_MODULE=config.settings.production` at runtime
- Never import from `config.settings` directly — always rely on `DJANGO_SETTINGS_MODULE`

## Django Conventions
- Fat models, thin views — business logic lives on the model or a service module, not in views or serializers
- All models extend `core.models.TimeStampedModel` (adds `created_at`, `updated_at`)
- Every model needs: `__str__`, `Meta.ordering`, meaningful `related_name`s on FK/M2M fields
- Use `select_related`/`prefetch_related` — never tolerate N+1 queries
- Migrations are never edited after being applied; flag destructive migrations before running
- Environment variables via `django-environ` only — never hardcode secrets

## DRF Conventions
- ViewSets + Routers for CRUD resources; `APIView` for custom logic
- Serializers own all validation — views stay thin
- Consistent error shape: `{ "error": string, "detail": any | null }`
- All endpoints under `/api/v1/`

## Key Domain Rules

### Reservations
- State machine: `pending → awaiting_payment → confirmed → checked_in → completed | cancelled | refunded`
- Conflict detection enforced at DB level — PostgreSQL exclusion constraint on `(room, tsrange(start_time, end_time))`
- Index `start_time`, `end_time`, and `room` FK on the Reservation model
- Stripe PaymentIntent ID stored on the Reservation; payment source of truth is Stripe
- **Never confirm a reservation on frontend redirect alone** — only on `payment_intent.succeeded` webhook
- Stale `awaiting_payment` reservations expire via django-q2 scheduled task (configurable TTL, default 15 min)

### Payments
- Stripe webhook at `/api/v1/payments/webhook/` — must be `csrf_exempt`, raw body, signature-verified
- Always use idempotency keys on Stripe API calls: `f"{reservation_id}-{action}"`
- Handle `payment_intent.succeeded` idempotently — check current state before transitioning
- `STRIPE_SECRET_KEY` and `STRIPE_WEBHOOK_SECRET` are backend-only env vars

### Waitlist
- Entries are ephemeral — auto-archive after configurable TTL (default 24 hours)
- SMS notifications abstracted behind a `NotificationService` interface — provider is swappable (Twilio default)

### Scheduled Tasks (django-q2)
- Uses Django ORM as broker — no Redis or external queue required
- Run the worker process alongside the Django server: `python manage.py qcluster`
- On Sevalla this runs as a second process in the same application
- Tasks live in `<app>/tasks.py` — keep them small and idempotent

## Commands
```bash
source .venv/bin/activate           # Activate virtual environment
python manage.py runserver          # Dev server
python manage.py qcluster           # Run django-q2 worker (separate terminal)
python manage.py migrate            # Run migrations
python manage.py makemigrations     # Generate migrations (review before committing)
pytest                              # Run all tests
pytest reservations/                # Run reservation tests only
pytest -x                          # Stop on first failure
```

## Environment Variables
See `.env.example` for all required vars. Never commit `.env`.
Critical vars: `DATABASE_URL`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `DJANGO_SETTINGS_MODULE`

## Testing Priorities
1. Reservation conflict detection logic
2. Payment state transitions (especially idempotency on webhook)
3. Waitlist state transitions
4. Auth flows (JWT issue, refresh, revoke)

## Footguns
- Stripe may deliver webhooks more than once — always guard state transitions idempotently
- Never skip webhook signature verification, even in dev (use Stripe CLI to forward events locally)
- PostgreSQL exclusion constraints require the `btree_gist` extension — enable it in a `RunSQL` operation in your initial migration: `CREATE EXTENSION IF NOT EXISTS btree_gist;`
- Sevalla injects env vars at runtime — missing vars fail silently until that code path is hit; keep `.env.example` current
- django-q2 worker must be running for scheduled tasks to execute — in dev you need two terminal tabs (one for `runserver`, one for `qcluster`)
- Custom user model must be set (`AUTH_USER_MODEL`) before the first `migrate` — impossible to change cleanly after migrations are applied
