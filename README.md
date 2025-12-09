## Voice Agent PSTN – Shifa Clinic Reception Assistant

`Voice-Agent-PSTN` is a production-style voice receptionist for clinics.

It connects to **LiveKit** to answer real phone calls, books / reschedules / cancels appointments, and exposes a clean **Flask dashboard** where human staff can manage patients, bookings, and see live call activity.

---

### Key Features

- **AI Phone Receptionist (LiveKit + LLM)**
  - Handles inbound PSTN calls in real time.
  - Collects caller **name** and **phone**, then books new appointments, reschedules, or cancels.
  - Maintains Redis-backed **session context** and **long‑term caller profiles**.

- **Receptionist Web Dashboard (Flask)**
  - Clean, responsive UI in HTML + CSS + vanilla JavaScript.
  - **Overview**: today’s appointment stats and high-level KPIs.
  - **Appointments** tab: full CRUD for bookings (create / edit / delete).
  - **Patients** tab: searchable patient directory with full CRUD.
  - **Live Calls** panel: shows active calls, booking stage, requested slot, and how long the call has been running.

- **Solid Backend Design**
  - SQLAlchemy models for `Patient` and `Appointment` with Flask‑Migrate migrations.
  - Service layer (`clinic_service`, `redis_service`) encapsulates DB and Redis logic.
  - LiveKit tools kept in `src/routes/livekit/tools.py` for a clear, testable agent API.

---

### Tech Stack

- **Backend**
  - Python 3.11+
  - Flask, Flask‑SQLAlchemy, Flask‑Migrate
  - Redis (session + caller profile store)
  - LiveKit Agents SDK + plugins (STT / LLM / TTS)

- **Frontend**
  - Jinja2 templates
  - Hand‑crafted HTML, CSS, and JavaScript (no frontend framework required)

---

### Project Structure (simplified)

Voice-Agent-PSTN/
  main.py                    # Flask dashboard entrypoint
  livekit_worker.py          # LiveKit worker entrypoint

  src/
    app_factory.py           # create_app(): Flask + DB + blueprints
    models/
      patient_db.py          # Patient model
      appointments_db.py     # Appointment model
    routes/
      livekit/
        main.py              # Agent configuration (LLM, tools, entrypoint)
        tools.py             # Function tools for booking / reschedule / cancel
      dashboard.py           # HTTP routes for dashboard + CRUD endpoints
    services/
      clinic_service.py      # Patient + appointment business logic
      redis_service.py       # BookingContext, CallerProfile, live sessions
      db_context.py          # Context manager for DB operations
      context_manager.py     # LiveKit ↔ BookingContext helpers

  src/templates/
    dashboard.html           # Main dashboard UI

  src/static/
    css/dashboard.css        # Dashboard styling (light theme)
    js/dashboard.js          # Search, modals, CRUD interactions---

### Installation

1. **Clone the repository**

git clone https://github.com/<your-org>/Voice-Agent-PSTN.git
cd Voice-Agent-PSTN2. **Install dependencies**

Using `uv` (recommended):

uv syncOr with `pip`:

python -m venv .venv
source .venv/bin/activate
pip install -e .3. **Configure environment**

Create a `.env` file in the project root (or export these in your shell):

FLASK_ENV=development

REDIS_HOST=localhost
REDIS_PORT=6379

# LiveKit / LLM / STT / TTS (examples)
LIVEKIT_URL=...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...

OPENAI_API_KEY=...
# etc.Make sure Redis is running:

redis-server---

### Running the System

You typically run **two processes**: one for the **AI worker** and one for the **dashboard**.

#### 1. LiveKit worker (AI receptionist)

cd /path/to/Voice-Agent-PSTN
uv run livekit_worker.pyThis process:

- Connects to LiveKit.
- Waits for incoming calls.
- Runs the voice agent defined in `src/routes/livekit/main.py`.
- Uses tools from `src/routes/livekit/tools.py` to read/write patients and appointments.

#### 2. Flask dashboard

cd /path/to/Voice-Agent-PSTN
uv run main.pyOpen in your browser:

http://localhost:5001/You will see:

- **Overview**: KPIs (total patients, today’s appointments, breakdown by status).
- **Appointments**: full-width table with **Add / Edit / Delete** (modal-based).
- **Patients**: searchable list with **Add / Edit / Delete**.
- **Live Calls**: table of active call sessions from Redis.

---

### Dashboard Capabilities

- **Patients**
  - Add patients from the Patients tab or via sidebar “+ New patient”.
  - Edit and delete via row actions, with confirmation prompts.
  - All persisted in the `patients` table via `clinic_service`.

- **Appointments**
  - Add appointments from Appointments tab or via sidebar “+ New appointment”.
  - Choose existing patient, date, time, and status (Booked / Pending / Rescheduled / Cancelled).
  - Edit and delete existing appointments with confirmation.

- **Live Calls**
  - Uses `list_active_sessions()` in `redis_service` to read `context:*` keys.
  - Shows:
    - Caller name / phone (if known),
    - Current `stage` (e.g. `start`, `collecting_phone`, `booking`, `rescheduling`),
    - Requested date/time slot,
    - “Started ago” (e.g. “3 min ago”).

---

### Tests

Run tests with:

uv run pytest
# or
pytestThe `tests/` directory includes unit tests; you can extend it with more coverage around tools and booking logic as you harden the agent.

---

### Configuration Notes

- **Database**
  - Default: SQLite (`instance/clinic.db`) for local development.
  - Migrations managed by Flask‑Migrate / Alembic in `migrations/`.
  - For production, configure Postgres/MySQL in `config.py`, run migrations, and point `SQLALCHEMY_DATABASE_URI` there.

- **Timezones & Slots**
  - Timezone and working-hour logic live in `clinic_service.py`.
  - Booking tools should:
    - Reject **past** date/time slots for new bookings.
    - Use `get_booked_slots` to avoid double‑booking.
    - Suggest a new slot when requested time is unavailable (configurable).

---

### Security & Production

- Run Flask behind a production WSGI server (Gunicorn, uWSGI) and a reverse proxy (Nginx).
- Store all API keys and secrets in environment variables or a secret manager.
- Always use HTTPS for the dashboard and LiveKit server URLs.
- Add auth (login) to the dashboard if it is reachable from outside your internal network.
- Review CORS, CSRF, and rate-limiting settings before exposing publicly.

---

### License

Specify your license here, for example:

MIT License – see LICENSE for details.