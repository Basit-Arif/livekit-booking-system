import os, json
import redis
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Optional, List, Dict
from src.models.patient_db import Patient
from src.models import Appointment
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

def load_caller_profile(phone: str) -> CallerProfile:
    """
    Load caller profile with fallback:
    1. Redis
    2. DB
    3. New profile
    Always returns CallerProfile (never None)
    """

    key = _caller_key(phone)
    raw = r.get(key)

    # 1️⃣ Redis
    if raw:
        try:
            data = json.loads(raw)
            return CallerProfile(**data)
        except Exception as e:
            print(f"[Redis] ⚠️ Corrupted profile for {phone}: {e}")

    # 2️⃣ Database
    with db_context():
        patient = Patient.query.filter_by(phone=phone).first()

        if patient:
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
                    "status": latest_appt.status if latest_appt else None,
                } if latest_appt else None,
            )

            save_caller_profile(profile)
            return profile

    # 3️⃣ Completely new caller
    profile = CallerProfile(phone=phone)
    save_caller_profile(profile)
    return profile

def upsert_caller_profile(phone: str, name: Optional[str] = None, last_appointment: Optional[dict] = None, ttl_sec: int = 604800) -> CallerProfile:
    """
    Merge-or-create a CallerProfile with provided phone, and optionally name/last_appointment.
    - Preserves existing fields unless new values are provided.
    - Updates last_seen timestamp.
    """
    if not phone:
        raise ValueError("phone is required for CallerProfile")
    existing = load_caller_profile(phone)
    if existing:
        if name:
            existing.name = name
        if last_appointment:
            existing.last_appointment = last_appointment
        existing.last_seen = datetime.utcnow().isoformat()
        save_caller_profile(existing, ttl_sec=ttl_sec)
        return existing
    profile = CallerProfile(
        name=name,
        phone=phone,
        last_appointment=last_appointment,
    )
    save_caller_profile(profile, ttl_sec=ttl_sec)
    return profile

# ✅ Data model for call context
@dataclass
class BookingContext:
    # Caller identity
    name: str | None = None
    phone: str | None = None

    # New booking request (OR new values during reschedule)
    date: str | None = None
    time: str | None = None
    suggested_slots: list[str] | None = None

    # State machine
    stage: str = "start"       # start | collecting_name | collecting_phone | got_time | booking | rescheduling
    status: str = "Pending"    # Pending | booked | rescheduled

    # 🔄 Reschedule mode fields
    mode: str = "normal"       # normal | reschedule
    old_date: str | None = None
    old_time: str | None = None
    new_date: str | None = None
    new_time: str | None = None
    reschedule_confirmed: bool = False
    confirmed_identity: bool = False
    cancel_appt_id: int | None = None

    # Metadata
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
    Hydrates session context:
    - loads CallerProfile (Redis → DB → new)
    - creates BookingContext for this call
    """

    if not phone:
        ctx = BookingContext(stage="ask_phone", status="Pending")
        save_context(caller_id, ctx)
        print("[Hydrate] No phone detected — asking caller.")
        return ctx

    # 👉 ALWAYS use load_caller_profile() (never duplicate logic)
    profile = load_caller_profile(phone)

    # Build session from profile
    session = BookingContext(
        name=profile.name,
        phone=profile.phone,
        date=None,
        time=None,
        status="returning" if profile.name else "new",
        stage="start",
    )

    save_context(caller_id, session)

    print(f"[Hydrate] 💾 Session hydrated for {caller_id}")
    return session


def list_active_sessions() -> List[Dict]:
    """
    Return a list of active call sessions from Redis for the dashboard.

    Each item includes:
    - participant_id
    - name / phone
    - stage / status
    - date / time (if known)
    - created_at and a human "started_ago" string
    """
    sessions: List[Dict] = []

    try:
        for key in r.scan_iter("context:*"):
            raw = r.get(key)
            if not raw:
                continue

            try:
                data = json.loads(raw)
                ctx = BookingContext(**data)
            except Exception:
                continue

            # participant_id is everything after "context:"
            participant_id = key.split(":", 1)[1] if ":" in key else key

            # Derive best date/time representation
            date = ctx.date or ctx.new_date or ctx.old_date
            time = ctx.time or ctx.new_time or ctx.old_time

            started_ago = ""
            try:
                created_dt = datetime.fromisoformat(ctx.created_at)
                delta = datetime.utcnow() - created_dt
                secs = int(delta.total_seconds())
                if secs < 60:
                    started_ago = "Just now"
                elif secs < 3600:
                    started_ago = f"{secs // 60} min ago"
                else:
                    started_ago = f"{secs // 3600} hr ago"
            except Exception:
                started_ago = ""

            sessions.append(
                {
                    "participant_id": participant_id,
                    "name": ctx.name,
                    "phone": ctx.phone,
                    "stage": ctx.stage,
                    "status": ctx.status,
                    "date": date,
                    "time": time,
                    "created_at": ctx.created_at,
                    "started_ago": started_ago,
                }
            )
    except Exception:
        # For dashboard display, it's fine to fail silently and show no sessions.
        return []

    # Sort newest first
    sessions.sort(key=lambda s: s.get("created_at") or "", reverse=True)
    return sessions
