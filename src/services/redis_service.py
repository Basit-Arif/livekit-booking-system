import os, json
import redis
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional
from src.models.patient_db import Patient
from src.services.db_context import db_context

# ✅ Redis connection setup
r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    db=0,
    decode_responses=True,
) 
# ===============================================================
# ☎️  LONG-TERM MEMORY (CallerProfile)
# ===============================================================
@dataclass
class CallerProfile:
    name: Optional[str] = None
    phone: Optional[str] = None
    last_appointment: Optional[dict] = None
    last_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

def _caller_key(phone: str) -> str:
    return f"caller:{phone}"

def save_caller_profile(profile: CallerProfile, ttl_sec: int = 604800):
    """Save caller profile (≈7 days TTL)."""
    if not profile.phone:
        return
    serialized = json.dumps(asdict(profile))
    r.setex(_caller_key(profile.phone), ttl_sec, serialized)
    print(f"[Redis] 💾 Saved caller profile for {profile.phone}")

def load_caller_profile(phone: str) -> Optional[CallerProfile]:
    """Load cached caller profile."""
    raw = r.get(_caller_key(phone))
    return CallerProfile(**json.loads(raw)) if raw else None

# ✅ Data model for call context
@dataclass
class BookingContext:
    name: str | None = None
    phone: str | None = None
    date: str | None = None
    time: str | None = None
    suggested_slots: list[str] | None = None
    stage: str = "start"
    status: str = "Pending"
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


# ✅ Helper for redis key formatting
def _key(pid: str) -> str:
    return f"context:{pid}"

# ✅ Load session context
def load_context(pid: str) -> BookingContext:
    raw = r.get(_key(pid))
    return BookingContext(**json.loads(raw)) if raw else BookingContext()

# ✅ Load session context if exists
def load_context_if_exists(pid: str) -> BookingContext | None:
    raw = r.get(_key(pid))
    return BookingContext(**json.loads(raw)) if raw else None

# ✅ Save session context with TTL = 5 minutes (300 seconds)
def save_context(pid: str, ctx: BookingContext, ttl_sec: int = 300):
    try:
        serialized = json.dumps(asdict(ctx))
        result = r.setex(_key(pid), ttl_sec, serialized)
        if result:
            print(f"[Redis] ✅ Saved context for {pid}")
            return True
        else:
            print(f"[Redis] ⚠️ Failed to save context for {pid}")
            return False
    except Exception as e:
        print(f"[Redis] ❌ Save error for {pid}: {e}")
        return False

# ✅ Delete session context manually
def clear_context(pid: str):
    r.delete(_key(pid))
    print(f"[Redis] Cleared context for {pid}")

# ✅ Participant ↔ context key mapping helpers
def _participant_map_key(participant_id: str) -> str:
    return f"participant_map:{participant_id}"

def set_participant_context_key(participant_id: str, context_key: str, ttl_sec: int = 300):
    r.setex(_participant_map_key(participant_id), ttl_sec, context_key)

def get_participant_context_key(participant_id: str) -> str | None:
    return r.get(_participant_map_key(participant_id))

def clear_participant_context_key(participant_id: str):
    r.delete(_participant_map_key(participant_id))

import re



def hydrate_context(caller_id: str, phone: str | None = None) -> BookingContext:
    """
    Hydrates call memory based on caller_id or phone.
    Priority:
    1️⃣ Redis CallerProfile (cached, 24h)
    2️⃣ DB Patient + Appointment (persistent)
    3️⃣ Fresh BookingContext (no history)
    """

    # 1️⃣ Case: No phone number detected (new SIP or unrecognized caller)
    if not phone:
        ctx = BookingContext(stage="ask_phone", status="Pending")
        save_context(caller_id, ctx)
        print(f"[Hydrate] 🚫 No phone detected — prompting caller to provide number.")
        return ctx

    # 2️⃣ Check Redis caller profile first
    profile = load_caller_profile(phone)
    if profile:
        print(f"[Hydrate] 🔁 Loaded caller profile from Redis: {profile.phone}")

    else:
        # 3️⃣ No Redis profile → check the database
        with db_context():
            patient = Patient.query.filter_by(phone=phone).first()

            if not patient:
                profile = CallerProfile(phone=phone)
                print(f"[Hydrate] 🆕 New caller — no patient record found for {phone}")

            else:
                # Fetch last known appointment
                latest_appt = (
                    Appointment.query.filter_by(patient_id=patient.id)
                    .order_by(Appointment.date.desc())
                    .first()
                )

                profile = CallerProfile(
                    name=patient.name,
                    phone=patient.phone,
                    last_appointment={
                        "date": str(latest_appt.date) if latest_appt else None,
                        "time": latest_appt.time if latest_appt else None,
                        "status": latest_appt.status if latest_appt else "N/A",
                    } if latest_appt else None,
                )

                print(f"[Hydrate] 🧠 Hydrated from DB — patient: {patient.name}")

            # Cache profile (new or existing) in Redis
            save_caller_profile(profile)

    # 4️⃣ Build session (short-term memory for this call)
    session = BookingContext(
        name=profile.name,
        phone=profile.phone,
        date=profile.last_appointment["date"] if profile.last_appointment else None,
        time=profile.last_appointment["time"] if profile.last_appointment else None,
        status="returning" if profile.name else "new",
        stage="start",
    )

    save_context(caller_id, session)
    print(f"[Hydrate] 💾 Saved session context for caller_id={caller_id}")
    return session
