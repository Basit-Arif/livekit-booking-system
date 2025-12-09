## Voice Agent PSTN – Shifa Clinic Reception Assistant

`Voice-Agent-PSTN` is a production-style voice receptionist for clinics.

It connects to **LiveKit** to answer real phone calls, books / reschedules / cancels appointments, and provides a clean **Flask dashboard** where staff can manage patients, appointments, and monitor live calls.

---

### Why this project?

Traditional phone reception is:

- Hard to scale during peak hours.
- Error‑prone when staff are busy.
- Expensive outside normal clinic times.

This project gives you:

- An **AI receptionist** that answers every call.
- A **single source of truth** for patients and appointments.
- A **simple web UI** where humans stay in control.

---

### Core Features

- **AI Phone Receptionist (LiveKit + LLM)**
  - Handles inbound PSTN calls in real time.
  - Collects caller **name** and **phone number**.
  - Books new appointments, reschedules existing ones, or cancels.
  - Uses Redis-backed **BookingContext** for per-call state and **CallerProfile** for memory across calls.

- **Receptionist Web Dashboard (Flask)**
  - Responsive, clean UI – HTML + CSS + vanilla JS (no heavy framework).
  - **Overview**:
    - Total patients.
    - Today’s appointments.
    - Booked / Pending / Rescheduled / Cancelled counts.
  - **Appointments** tab:
    - Full CRUD: create, edit, delete bookings.
    - Modal form with patient selector, date, time, and status.
  - **Patients** tab:
    - Search by name/phone.
    - Full CRUD: add, edit, delete patients.
  - **Live Calls** panel:
    - See active AI calls, current stage, requested slot, and how long they’ve been running.

- **Backend & Persistence**
  - SQLAlchemy models for `Patient` and `Appointment`.
  - Flask‑Migrate / Alembic migration setup.
  - `clinic_service` encapsulates all DB logic around appointments and patients.
  - `redis_service` encapsulates Redis usage and session listing for the dashboard.

---

### Tech Stack

- **Runtime**
  - Python 3.11+

- **Backend**
  - Flask
  - Flask‑SQLAlchemy
  - Flask‑Migrate
  - Redis
  - LiveKit Agents SDK + plugins (STT / LLM / TTS)

- **Frontend**
  - Jinja2 templates
  - HTML, CSS, JavaScript

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
        main.py              # Voice agent setup (LLM, tools, entrypoint)
        tools.py             # Tools: save_name, save_phone, booking_appointment, etc.
      dashboard.py           # HTTP routes for dashboard & CRUD

    services/
      clinic_service.py      # Patient + appointment business logic
      redis_service.py       # BookingContext, CallerProfile, live sessions
      db_context.py          # Context manager for DB sessions
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

Create a `.env` file in the project root (or export equivalent env vars):

FLASK_ENV=development

REDIS_HOST=localhost
REDIS_PORT=6379

# LiveKit / LLM / STT / TTS (examples)
LIVEKIT_URL=...
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...

OPENAI_API_KEY=...
# etc.Ensure Redis is running locally:

redis-server---

### Running the System

You typically run **two processes**: the LiveKit worker and the Flask dashboard.

#### 1. LiveKit worker (AI receptionist)

cd /path/to/Voice-Agent-PSTN
uv run livekit_worker.pyThis process:

- Connects to your LiveKit server.
- Waits for incoming calls.
- Runs the agent defined in `src/routes/livekit/main.py`.
- Uses the tools in `src/routes/livekit/tools.py` for all booking / reschedule / cancel logic.

#### 2. Flask dashboard

cd /path/to/Voice-Agent-PSTN
uv run main.pyThen open:

http://localhost:5001/You’ll have:

- **Overview** – summary cards and today’s schedule.
- **Appointments** – full-width table with Add / Edit / Delete.
- **Patients** – searchable list with Add / Edit / Delete.
- **Live Calls** – real-time view of current AI calls.

---

### Dashboard Details

#### Patients

- Add patients using:
  - “+ New patient” in the sidebar, or
  - “+ Add patient” in the Patients panel.
- Edit:
  - Opens a modal pre-filled with current name / phone / email.
- Delete:
  - Pops a confirm dialog, then deletes via `POST /patients/<id>/delete`.

#### Appointments

- Add appointments using:
  - “+ New appointment” in the sidebar, or
  - “+ Add appointment” in the Appointments panel.
- Choose:
  - Existing patient,
  - Date (`YYYY-MM-DD`),
  - Time (`e.g. 10:30 am`),
  - Status (Booked / Pending / Rescheduled / Cancelled).
- Edit / Delete:
  - Row actions with confirmation before destructive actions.

#### Live Calls

- Backed by `list_active_sessions()` in `redis_service.py`.
- Shows, per active call:
  - Caller name and phone (if known),
  - Current booking `stage`,
  - Current `status`,
  - Requested `date` / `time` (if already provided),
  - How long ago the call started.

---

### Tests

Run the test suite with:

uv run pytest
# or
pytestExtend `tests/` with additional coverage as you modify booking rules or LiveKit tools.

---

### Configuration Notes

- **Database**
  - Default: SQLite at `instance/clinic.db` for local development.
  - Migrations managed via Flask‑Migrate / Alembic in `migrations/`.
  - For production, update `config.py` to use Postgres/MySQL and run migrations.

- **Timezones & Appointment Rules**
  - Timezone (e.g. `Asia/Karachi`) and time-slot logic live in `clinic_service.py`.
  - Booking tools are designed to:
    - Reject **past** date/time slots for new appointments.
    - Respect clinic working hours.
    - Check `get_booked_slots` to avoid double-booking.
    - Suggest alternative slots when a requested time is unavailable.

---

### Security & Production

Before putting this into production:

- Run Flask under Gunicorn/uWSGI behind Nginx (HTTPS).
- Keep API keys and secrets out of source control (env vars / secret manager only).
- Protect the dashboard with authentication if it’s not strictly internal.
- Review:
  - CORS / CSRF,
  - Rate-limiting for APIs,
  - Logging and monitoring.

---

### License

Specify your license, for example:

MIT License – see LICENSE for details.