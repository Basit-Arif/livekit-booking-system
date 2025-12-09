### Voice Agent PSTN – Shifa Clinic Reception Assistant

`Voice-Agent-PSTN` is a production-style voice receptionist for clinics.  
It answers real phone calls via LiveKit, books/reschedules/cancels appointments, and exposes a Flask web dashboard for reception staff to manage patients and bookings.

---

### Features

- **AI Phone Receptionist (LiveKit + LLM)**
  - Handles inbound PSTN calls in real time.
  - Collects caller name and phone, books new appointments, reschedules, or cancels.
  - Uses Redis-backed session context and long‑term caller profiles.

- **Receptionist Web Dashboard (Flask)**
  - Clean, responsive UI in pure HTML/CSS/JS.
  - **Today’s overview**: total patients, today’s appointments, status breakdown.
  - **Patients tab**: searchable list with manual **create / edit / delete**.
  - **Appointments tab**: manual **create / edit / delete** for bookings.
  - **Live calls panel**: shows active calls, caller info, booking stage, and requested slot.

- **Database & Persistence**
  - SQLite / SQLAlchemy models for `Patient` and `Appointment`.
  - Flask-Migrate for migrations, `db_context` helper for safe app context usage.
  - Redis for per-call `BookingContext` and permanent `CallerProfile`.

- **Production‑friendly structure**
  - Clear separation of `routes`, `services`, and `models`.
  - Independent entrypoints for the LiveKit worker and Flask app.
  - Logging + simple latency tracking hooks.

---

### Tech Stack

- **Backend**
  - Python 3.11+
  - Flask
  - Flask‑SQLAlchemy
  - Flask‑Migrate
  - Redis (session + profiles)
  - LiveKit Agents SDK + plugins (STT/LLM/TTS)

- **Frontend**
  - Jinja2 templates
  - Hand‑written HTML, CSS, and vanilla JavaScript  
  - No frontend frameworks required

---

### Project Structure (simplified)

Voice-Agent-PSTN/
  main.py                    # Flask dashboard entrypoint
  livekit_worker.py          # LiveKit worker entrypoint
  src/
    app_factory.py           # create_app(): Flask app + DB
    models/
      patient_db.py          # Patient model
      appointments_db.py     # Appointment model
    routes/
      livekit/
        main.py              # Agent setup (LLM, tools, entrypoint)
        tools.py             # Function tools for booking, reschedule, cancel, etc.
      dashboard.py           # HTTP routes for dashboard + CRUD
    services/
      clinic_service.py      # Patient + appointment helpers
      redis_service.py       # BookingContext, CallerProfile, live sessions
      db_context.py          # Context manager for DB operations
      context_manager.py     # LiveKit ↔ BookingContext helpers
  src/templates/
    dashboard.html           # Main dashboard UI
  src/static/
    css/dashboard.css        # Dashboard styling (light theme)
    js/dashboard.js          # Search, modals, CRUD UX---

### Installation

1. **Clone the repo**

git clone https://github.com/<your-org>/Voice-Agent-PSTN.git
cd Voice-Agent-PSTN2. **Install dependencies**

Using `uv` (recommended):

uv syncOr with `pip`:

python -m venv .venv
source .venv/bin/activate
pip install -e .3. **Set environment variables**

Create a `.env` file (or export in your shell):

FLASK_ENV=development
REDIS_HOST=localhost
REDIS_PORT=6379

# LiveKit / LLM / STT / TTS config (examples)
LIVEKIT_URL=...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...

OPENAI_API_KEY=...
# etc.Make sure Redis is running:

redis-server---

### Running the System

You typically run **two processes**: one for the voice worker, one for the dashboard.

#### 1. Start the LiveKit worker (AI receptionist)

cd /path/to/Voice-Agent-PSTN
uv run livekit_worker.pyThis process:

- Connects to LiveKit.
- Waits for calls and runs the agent defined in `src/routes/livekit/main.py`.
- Uses tools from `src/routes/livekit/tools.py` to manipulate patients/appointments.

#### 2. Start the Flask dashboard

cd /path/to/Voice-Agent-PSTN
uv run main.pyOpen in your browser:

http://localhost:5001/You’ll see:

- **Overview** tab with today’s KPIs and mixed view of appointments + patients.
- **Appointments** tab with a full-width table and CRUD modal.
- **Patients** tab with patient search and CRUD modal.
- **Live Calls** panel showing active BookingContexts from Redis.

---

### Dashboard Highlights

- **Manual Patient CRUD**
  - “Add patient” buttons in the Patients panel and sidebar.
  - Modal form validates name/phone/email and posts to `/patients/save`.
  - Each row supports **Edit** (modal pre-filled) and **Delete** (with confirmation).

- **Manual Appointment CRUD**
  - “Add appointment” buttons in the Appointments panel and sidebar.
  - Modal form selects an existing patient, date, time, and status.
  - Per-row **Edit** and **Delete** with confirmation dialogs.

- **Live Calls Panel**
  - Reads Redis keys `context:*` via `list_active_sessions()`.
  - Shows caller name, phone, current stage (`start`, `collecting_phone`, `booking`, etc.), requested slot, and how long the call has been active.

---

### Tests

Basic tests live in `tests/`:

uv run pytest
# or
pytestAdd more tests around booking logic and tools as you harden the agent for production.

---

### Configuration Notes

- **Database**
  - Default is SQLite (via `instance/clinic.db`) for local development.
  - Use Flask-Migrate + Alembic (`migrations/`) to evolve schema.
  - For production, switch to Postgres/MySQL in `config.py` and run migrations.

- **Timezones & Slots**
  - The clinic timezone and working hours are configured in `clinic_service.py`.
  - Booking tools must respect:
    - Valid working hours.
    - No past date/time when creating new appointments.
    - Slot availability based on `get_booked_slots`.

---

### Security & Production Considerations

- Run Flask behind a real web server (e.g. Nginx + Gunicorn or uWSGI).
- Store API keys and secrets in a secure config (env vars or secret manager).
- Use HTTPS for dashboard and LiveKit URLs.
- Harden CORS, CSRF, and authentication if exposing the dashboard on the public internet.

---

### License

Specify your license here, e.g.:

MIT License – see LICENSE file for details.