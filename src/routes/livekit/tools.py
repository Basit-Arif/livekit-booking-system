from livekit.agents import Agent, AgentSession, JobContext, function_tool
from src.services.context_manager import _ctx,_save,_clear
from pydantic import ValidationError
from pydantic import BaseModel, Field,validator
from typing import Optional
import logging
from datetime import datetime,timedelta
from src.services.clinic_service import get_or_create_patient,create_appointment,get_patient_by_phone
from src.services.db_context import db_context
logger = logging.getLogger("voice_agent.tools")


@function_tool
async def save_name(name: str) -> str:
    """Store validated patient name in Redis with detailed logging."""
    ctx = _ctx()
    
    try:
        # ✅ Validate name via Pydantic
        validated = BookingBase(name=name)
        ctx.name = validated.name.strip().title()

        # ✅ Save updated context
        _save(ctx)
        logger.info(f"[save_name] ✅ Saved context fo {ctx}")

        return f"Got it, {ctx.name}."

    except ValidationError as e:
        logger.warning(f"[save_name] ❌ Validation failed for name={name!r}: {e}")
        return "I might have misheard your name. Could you please repeat it clearly?"

    except Exception as e:
        logger.exception(f"[save_name] 💥 Unexpected error while saving name: {e}")
        return "Sorry, something went wrong while saving your name. Could you repeat it?"


@function_tool
async def save_phone(phone: str) -> str:
    """Store validated patient phone in Redis using existing BookingBase validator."""
    ctx = _ctx()
    logger.info(f"[save_phone] 📞 Called for participant:")
    logger.info(f"[save_phone] Raw phone input: {phone!r}")

    try:
        # ✅ Validation handled by your existing Pydantic model
        validated = BookingBase(phone=phone)

        # Save normalized/validated value
        ctx.phone = validated.phone
        _save(ctx)
        logger.info(f"[save_phone] ✅ Saved context for {ctx}")

        # Send a natural signal back to the LLM
        return f"Got it, your phone number is {ctx.phone}."

    except ValidationError as e:
        logger.warning(f"[save_phone] ❌ Validation failed for phone={phone!r}: {e}")
        return "That number doesn’t seem right. Could you please repeat your phone number?"

    except Exception as e:
        logger.exception(f"[save_phone] 💥 Unexpected error: {e}")
        return "Sorry, something went wrong while saving your phone number. Could you repeat it?"




def parse_time_range(text: str):
    """Extract a time range or single time (e.g. 2pm, 14:00, between 2 and 3)."""
    pattern = r'(\d{1,2})(?::(\d{2}))?\s*(am|pm)?'
    matches = re.findall(pattern, text.lower())
    if not matches:
        return None, None

    def to_24h(h, m, meridian):
        h, m = int(h), int(m or 0)
        if meridian == "pm" and h != 12:
            h += 12
        elif meridian == "am" and h == 12:
            h = 0
        return h, m

    if len(matches) == 1:
        h1, m1 = to_24h(*matches[0])
        return (h1, m1), None
    elif len(matches) >= 2:
        h1, m1 = to_24h(*matches[0])
        h2, m2 = to_24h(*matches[1])
        return (h1, m1), (h2, m2)
    return None, None


@function_tool
async def available_slot(day: str = "", date: str = "", time: str = "") -> str:
    """
    Suggest appointment slots conversationally.
    Supports 'morning', 'afternoon', 'evening', and specific hour ranges.
    """
    ctx = _ctx()
    today = datetime.now()
    user_text = " ".join(filter(None, [day, date, time])).lower().strip()
    logger.info(f"[available_slot] 🧠 User said: {user_text!r}")

    # Detect date
    if "today" in user_text:
        target_date = today
    elif "tomorrow" in user_text:
        target_date = today + timedelta(days=1)
    else:
        try:
            target_date = datetime.strptime(date, "%Y-%m-%d")
        except Exception:
            target_date = today

    formatted_date = target_date.strftime("%Y-%m-%d")
    spoken_day = target_date.strftime("%A, %B %d")

    # Define all working slots
    all_slots = [
        "9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM",
        "11:00 AM", "11:30 AM", "12:00 PM",
        "1:00 PM", "1:30 PM", "2:00 PM", "2:30 PM",
        "3:00 PM", "3:30 PM", "4:00 PM"
    ]

    # Keyword filtering
    if "morning" in user_text:
        slots = [s for s in all_slots if "AM" in s]
    elif "afternoon" in user_text:
        slots = [s for s in all_slots if "PM" in s and int(s.split(':')[0]) < 4]
    elif "evening" in user_text:
        slots = [s for s in all_slots if "PM" in s and int(s.split(':')[0]) >= 4]
    else:
        # Parse specific time or range
        start, end = parse_time_range(user_text)
        if start:
            def slot_to_24h(slot):
                h, m = map(int, re.findall(r"\d+", slot))
                if "PM" in slot and h != 12:
                    h += 12
                elif "AM" in slot and h == 12:
                    h = 0
                return h, m

            slots = []
            for s in all_slots:
                sh, sm = slot_to_24h(s)
                if end:
                    # Range case: e.g. between 2:00 PM and 3:00 PM
                    if (sh, sm) >= start and (sh, sm) <= end:
                        slots.append(s)
                else:
                    # Single hour ±30 min window
                    start_h, start_m = start
                    if abs((sh * 60 + sm) - (start_h * 60 + start_m)) <= 30:
                        slots.append(s)

            if not slots:
                slots = all_slots  # fallback

        else:
            slots = all_slots

    # Save suggestions to Redis
    ctx.suggested_slots = slots[:3]
    ctx.date = formatted_date
    _save(ctx)
    logger.info(f"[available_slot] 💾 Saved to Redis → {ctx}")

    # Build natural response
    readable = ", ".join(ctx.suggested_slots[:-1]) + f", or {ctx.suggested_slots[-1]}" if len(ctx.suggested_slots) > 1 else ctx.suggested_slots[0]
    return f"On {spoken_day}, I have {readable} available. Which one would you like to book?"

@function_tool
async def booking_appointment(time: str = "") -> str:
    """
    Confirm or reschedule an appointment.
    Async + production-safe version.
    """
    ctx = _ctx()

    try:
        # 0️⃣ Require phone before booking
        if not ctx.phone or len(ctx.phone.strip()) < 10:
            return (
                "Before booking, I’ll need your phone number to confirm your appointment. "
                "Could you please share your contact number?"
            )

        # 1️⃣ Determine selected time
        selected_time = time or (ctx.suggested_slots[0] if ctx.suggested_slots else None)
        if not selected_time:
            return "I don’t have a time selected yet. Which slot would you like to book?"

        greeting = ""
        patient_data = None

        # 2️⃣ Query DB safely inside context
        with db_context():
            existing_patient = get_patient_by_phone(ctx.phone)

            if existing_patient:
                patient_data = {
                    "id": existing_patient.id,
                    "name": existing_patient.name,
                }
                logger.info(f"[booking_appointment] Returning patient: {patient_data['name']}")
            else:
                new_patient = get_or_create_patient(ctx.name, ctx.phone)
                patient_data = {
                    "id": new_patient.id,
                    "name": new_patient.name,
                }
                greeting = f"Got it, {ctx.name}. I’ve created your new record. "
                logger.info(f"[booking_appointment] New patient: {patient_data['name']}")

            # 3️⃣ Prevent duplicate same-day bookings
            existing_appt = (
                Appointment.query.filter_by(patient_id=patient_data["id"], date=ctx.date).first()
            )

            if existing_appt:
                if existing_appt.time == selected_time:
                    return (
                        f"You already have an appointment on {ctx.date} at {existing_appt.time}. "
                        "Would you like to reschedule?"
                    )

                # Reschedule
                existing_appt.time = selected_time
                existing_appt.status = "Rescheduled"
                db.session.commit()
                ctx.time = selected_time
                ctx.status = "rescheduled"
                _save(ctx)
                return (
                    f"{greeting}Your appointment has been rescheduled to {ctx.date} at {selected_time}. "
                    "We’ll send you a confirmation shortly."
                )

            # 4️⃣ Create new appointment
            new_appt = Appointment(
                patient_id=patient_data["id"],
                date=ctx.date,
                time=selected_time,
                status="Booked",
                created_at=datetime.utcnow(),
            )
            db.session.add(new_appt)
            db.session.commit()

        # 5️⃣ Update Redis (non-blocking)
        ctx.time = selected_time
        ctx.status = "booked"
        asyncio.create_task(asyncio.to_thread(_save, ctx))

        logger.info(f"[booking_appointment] ✅ Booked {ctx.name} at {ctx.date} {ctx.time}")

        return (
            f"{greeting}"
            f"Your appointment has been booked for {ctx.date} at {ctx.time}. "
            "We’ll send you a confirmation shortly."
        )

    except Exception as e:
        logger.error(f"[booking_appointment] ❌ Error: {e}")
        return "Sorry, something went wrong while booking your appointment."


@function_tool
async def get_date():
    """Return system date and time."""
    return f"Today's date is {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}"


import re

class BookingBase(BaseModel):
    name: Optional[str] = Field(None, description="Customer name")     
    phone: Optional[str] = Field(None, descripton="Customer Phone number")

    @validator("name")
    def validate_name(cls, v):
        # Must contain at least 2 letters and no digits/special chars
        if not re.match(r"^[A-Za-z\s]{2,50}$", v.strip()):
            raise ValueError("Invalid name format. Only letters allowed.")
        return v.strip().title()

    # --- phone validation ---
    @validator("phone")
    def validate_phone(cls, v):
        # Accept Pakistani or international numbers (digits, optional +, -, spaces)
        clean = re.sub(r"[^\d+]", "", v)
        if len(clean) < 10 or len(clean) > 15:
            raise ValueError("Invalid phone number length.")
        if not re.match(r"^\+?\d{10,15}$", clean):
            raise ValueError("Invalid phone number format.")
        return clean

class BookingCreate(BookingBase):
    date: str = Field(..., description="Appointment date in YYYY-MM-DD format")
    time: str = Field(..., description="Appointment time in HH:MM format (24-hour)")

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in format YYYY-MM-DD.")
        return v

    @validator("time")
    def validate_time(cls, v):
        if not re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", v):
            raise ValueError("Time must be in format HH:MM (24-hour).")
        return v