from livekit.agents import Agent, AgentSession, JobContext, function_tool
from livekit.agents import get_job_context
from livekit import api
from src.services.context_manager import _ctx,_save,_clear, CURRENT_PARTICIPANT
from pydantic import ValidationError
from pydantic import BaseModel, Field,validator
from typing import Optional
import logging
from datetime import datetime,timedelta
from src.services.clinic_service import get_or_create_patient,create_appointment,get_patient_by_phone,get_upcoming_appointment,reschedule_appointment,get_booked_slots,delete_appointment
from src.services.db_context import db_context
from extensions import db
from src.models import Appointment
import asyncio
from src.services.redis_service import upsert_caller_profile

logger = logging.getLogger("voice_agent.tools")

async def hangup_call():
    ctx = get_job_context()
    if ctx is None:
        return
    try:
        logger.info(f"[end_call] Deleting room: {ctx.room.name}")
        await ctx.api.room.delete_room(
            api.DeleteRoomRequest(
                room=ctx.room.name,
            )
        )
        logger.info(f"[end_call] Room deleted: {ctx.room.name}")
    except Exception as e:
        logger.warning(f"[end_call] delete_room failed: {e}. Trying remove_participant by identity…")
        try:
            identity = CURRENT_PARTICIPANT.get(None) or ""
            if identity:
                await ctx.api.room.remove_participant(
                    api.RemoveParticipantRequest(
                        room=ctx.room.name,
                        identity=identity,
                    )
                )
                logger.info(f"[end_call] Removed participant identity={identity}")
            else:
                logger.error("[end_call] No participant identity available to remove.")
        except Exception as e2:
            logger.exception(f"[end_call] remove_participant failed: {e2}")

@function_tool
async def save_name(name: str) -> str:
    ctx = _ctx()

    try:
        # Block name saving in reschedule flow
        if ctx.mode == "reschedule":
            return "You're rescheduling your appointment. Tell me the new date and time you want to move it to."

        # Block name saving in cancel flow
        if ctx.mode == "cancel":
            return "You're cancelling your appointment. I only need your phone number to find your record."

        # Validate name
        validated = BookingBase(name=name)
        ctx.name = validated.name
        _save(ctx)

        return f"Thanks, {ctx.name}."

    except ValidationError as e:
        logger.warning(f"[save_name] validation_failed name={name!r} error={e}")
        return "I didn't catch that clearly. Please say your name again."

    except Exception as e:
        logger.exception(f"[save_name] unexpected_error name={name!r} error={e}")
        return "Sorry, something went wrong. Please repeat your name."


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
async def available_slot(day: Optional[str] = None, date: Optional[str] = None, time: Optional[str] = None) -> str:
    """
    Suggest available appointment slots for a given day.
    - Understands natural language ("tomorrow", "morning", "after 2pm")
    - Always fetches fresh availability from DB.
    - Returns top 3 free slots.
    - Stores them in ctx.suggested_slots for booking_appointment.
    """

    ctx = _ctx()
    # Normalize missing values to empty strings for downstream logic
    day = day or ""
    date = date or ""
    time = time or ""
    logger.info(f"[available_slot] ▶ Input: day={day!r}, date={date!r}, time={time!r}")

    try:
        # -------------------------------------------
        # 1️⃣ Resolve target date naturally
        # -------------------------------------------
        today = datetime.now()
        user_text = " ".join(filter(None, [day, date, time])).lower().strip()

        if "today" in user_text:
            target = today
        elif "tomorrow" in user_text:
            target = today + timedelta(days=1)
        else:
            try:
                target = datetime.strptime(date, "%Y-%m-%d")
            except Exception:
                # fallback: nearest future day
                target = today

        if target.date() < today.date():
            return "I can't book for past dates. Please choose a future date."

        if target > today + timedelta(days=30):
            return "I can book up to 30 days ahead. Please give a closer date."

        ctx.date = target.strftime("%Y-%m-%d")
        _save(ctx)

        spoken_day = target.strftime("%A, %B %d")

        # -------------------------------------------
        # 2️⃣ Base clinic working hours
        # -------------------------------------------
        ALL_SLOTS = [
            "9:00 AM", "9:30 AM", "10:00 AM", "10:30 AM",
            "11:00 AM", "11:30 AM", "12:00 PM",
            "1:00 PM", "1:30 PM", "2:00 PM", "2:30 PM",
            "3:00 PM", "3:30 PM", "4:00 PM"
        ]

        # -------------------------------------------
        # 3️⃣ Natural filtering (morning/evening etc.)
        # -------------------------------------------
        lower = user_text.lower()
        filtered = ALL_SLOTS.copy()

        if "morning" in lower:
            filtered = [s for s in ALL_SLOTS if "AM" in s]
        elif "afternoon" in lower:
            filtered = [s for s in ALL_SLOTS if "PM" in s and int(s.split(":")[0]) < 4]
        elif "evening" in lower:
            filtered = [s for s in ALL_SLOTS if "PM" in s and int(s.split(":")[0]) >= 4]
        else:
            # Time-based filtering (e.g., "after 2")
            try:
                numbers = re.findall(r"\d+", lower)
                if numbers:
                    hour = int(numbers[0])
                    filtered = [s for s in ALL_SLOTS if int(s.split(":")[0]) >= hour]
            except Exception:
                pass

        # -------------------------------------------
        # 4️⃣ Remove already booked slots (live DB)
        # -------------------------------------------
        booked = get_booked_slots(ctx.date) or []
        logger.info(f"[available_slot] Booked slots for {ctx.date}: {booked}")

        fresh_available = [s for s in filtered if s not in booked]

        # If the user filtered too much & no slots remain → fallback to all free slots
        if not fresh_available:
            fresh_available = [s for s in ALL_SLOTS if s not in booked]

        # Still empty → fully booked
        if not fresh_available:
            return f"All slots on {spoken_day} are full. Would you like another day?"

        # -------------------------------------------
        # 5️⃣ Pick top 3 best options
        # -------------------------------------------
        top3 = fresh_available
        ctx.suggested_slots = top3
        _save(ctx)

        if len(top3) == 1:
            readable = top3[0]
        else:
            readable = ", ".join(top3[:-1]) + f", or {top3[-1]}"

        logger.info(f"[available_slot] Final suggestions: {top3}")

        return f"On {spoken_day}, I have {readable} available. Which time works best for you?"
    except Exception as e:
        logger.exception(f"[available_slot] Unexpected error: {e}")
        return "I’m having trouble checking availability right now. Please try again in a moment."

@function_tool
async def booking_appointment(date: str = "", time: str = "") -> str:
    """
    Final booking step: create the appointment.
    Assumes:
    - name is known
    - phone is known
    - date is set
    - time is set
    LLM handles all questioning BEFORE calling this tool.
    """

    ctx = _ctx()  # Redis session memory
    if time:
        ctx.time = time

    # Optional: allow LLM to pass/override the date directly
    if date:
        try:
            # Expect YYYY-MM-DD format (same as BookingCreate / DB)
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return "The date should be in YYYY-MM-DD format, like 2025-11-25."
        ctx.date = date

    _save(ctx)

    try:
        # -----------------------------
        # 1️⃣ Validate required fields
        # -----------------------------
        if not ctx.phone:
            return "I still need your phone number."

        if not ctx.name:
            return "I still need your name."

        if not ctx.date:
            return "I still need the date."

        if not ctx.time:
            return "I still need the time."

        selected_time = ctx.time

        # -----------------------------
        # 2️⃣ Fetch or create patient
        # -----------------------------
        with db_context():
            patient = get_patient_by_phone(ctx.phone)

            if not patient:
                # Create new patient
                patient = get_or_create_patient(ctx.name, ctx.phone)
                if not patient:
                    logger.error(
                        f"[booking] get_or_create_patient failed for name={ctx.name!r}, phone={ctx.phone!r}"
                    )
                    return "Sorry, I couldn't access our booking system. Please try again."

                logger.info(f"[booking] Created new patient: {patient}")

            patient_id = patient["id"]

            # -----------------------------
            # 3️⃣ Check if appointment exists
            # -----------------------------
            existing = Appointment.query.filter_by(
                patient_id=patient_id,
                date=ctx.date
            ).first()

            if existing:
                if existing.time == selected_time:
                    return (
                        f"You already have an appointment on {ctx.date} at {selected_time}. "
                        "Would you like to change it?"
                    )
                else:
                    return (
                        f"You have an appointment on {ctx.date} at {existing.time}. "
                        f"Should I move it to {selected_time}?"
                    )

            # -----------------------------
            # 4️⃣ Create appointment
            # -----------------------------
            new_appt = create_appointment(
                patient_id=patient_id,
                date=ctx.date,
                time=selected_time
            )

            if not new_appt:
                logger.error(
                    f"[booking] create_appointment returned None for patient_id={patient_id}, "
                    f"date={ctx.date}, time={selected_time}"
                )
                return "Sorry, I couldn't complete the booking. Please try again."

            logger.info(f"[booking] Appointment created: {new_appt}")




        ctx.status = "BOOKED"
        ctx.stage = "DONE"

        asyncio.create_task(asyncio.to_thread(_save, ctx))

        return (
            f"Your appointment is confirmed for {ctx.date} at {selected_time}. "
            "Anything else you need?"
        )

    except Exception as e:
        logger.error(f"[booking] ❌ Error: {e}")
        return "Sorry, I couldn't complete the booking. Please try again."


@function_tool
async def get_date():
    """Return system date and time."""
    return f"Today's date is {datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}"


@function_tool
async def update_caller_profile(name: Optional[str] = None, phone: Optional[str] = None) -> str:
    """
    Persist caller profile (name/phone) for future calls without disrupting session.
    If phone not provided, uses current session phone if available.
    """
    ctx = _ctx()
    target_phone = (phone or ctx.phone or "").strip()
    target_name = (name or ctx.name or "").strip()

    if not target_phone:
        return "I need a phone number to update your profile. What’s your number?"

    try:
        profile = upsert_caller_profile(phone=target_phone, name=target_name or None)
        # Merge back to session for immediate continuity
        if target_name:
            ctx.name = target_name.title()
        ctx.phone = profile.phone
        _save(ctx)
        if target_name:
            return f"Okay, I’ll remember {ctx.name} for next time."
        return "Okay, I’ll remember your details for next time."
    except Exception as e:
        logger.exception(f"[update_caller_profile] Failed: {e}")
        return "Sorry, I couldn’t update your profile right now."

@function_tool
async def confirm_reschedule(time: str = "") -> str:
    """
    Confirm and perform rescheduling to the selected date/time.
    Use after start_reschedule + available_slot when the caller says 'yes'.
    """
    ctx = _ctx()

    if not ctx.phone:
        return "I need your phone number to find your appointment. What’s your number?"

    if not ctx.date:
        return "Which date should I move your appointment to?"

    # Determine the target time
    selected_time = time or (ctx.suggested_slots[0] if ctx.suggested_slots else ctx.time)
    if not selected_time:
        return "Which time should I move it to?"

    try:
        with db_context():
            patient = get_patient_by_phone(ctx.phone)
            if not patient:
                return "we don't have your record,do you want to book a new one?"

            upcoming = get_upcoming_appointment(patient["id"])
            if not upcoming:
                return "I don’t see an upcoming appointment to move. Should I book a new one instead?"

            old_date, old_time = str(upcoming.date), upcoming.time
            updated_appt = reschedule_appointment(upcoming.id, ctx.date, selected_time)

            if not updated_appt:
                logger.error(
                    f"[confirm_reschedule] reschedule_appointment returned None for appt_id={upcoming.id}, "
                    f"new_date={ctx.date}, new_time={selected_time}"
                )
                return "Sorry, I couldn’t change that appointment right now. Please try again later."

        ctx.time = selected_time
        ctx.status = "rescheduled"
        _save(ctx)

        return (
            f"Done. I’ve moved your appointment from {old_date} at {old_time} "
            f"to {ctx.date} at {selected_time}. Anything else I can help with?"
        )
    except Exception as e:
        logger.exception(f"[confirm_reschedule] Unexpected error: {e}")
        return "Sorry, I couldn’t change that appointment right now. Please try again later."
@function_tool
async def end_call() -> str:
    """
    Gracefully end the call after confirming there's nothing else needed.
    Does not clear Redis; short-term memory expires via TTL.
    """
    async def _delayed_hangup():
        try:
            await asyncio.sleep(1.0)  # allow TTS to finish
            await hangup_call()
        except Exception as e:
            logger.exception(f"[end_call] Hangup task failed: {e}")
    asyncio.create_task(_delayed_hangup())
    return "Thanks for calling Shifa Clinic. Goodbye."

import re



@function_tool 
async def start_reschedule() -> str:
    ctx = _ctx()

    if not ctx.phone:
        return "Sure, I can help with that. Can you confirm your phone number first?"

    try:
        with db_context():
            patient = get_patient_by_phone(ctx.phone)

            if not patient:
                return "I couldn’t find your record. Can you share your name?"

            upcoming = get_upcoming_appointment(patient["id"])

            if not upcoming:
                return "You don’t have any upcoming appointment. Would you like to book a new one?"

            # Convert date
            try:
                old_date = datetime.strptime(upcoming.date, "%Y-%m-%d").strftime("%B %d")
            except Exception:
                old_date = upcoming.date  # fallback

            # Format time nicely
            try:
                old_time = datetime.strptime(upcoming.time, "%H:%M").strftime("%I:%M %p")
            except Exception:
                old_time = upcoming.time

            ctx.old_date = old_date
            ctx.old_time = old_time
            ctx.mode = "reschedule"
            _save(ctx)

            return f"I found your appointment on {old_date} at {old_time}. What date and time would you like to move it to?"
    except Exception as e:
        logger.exception(f"[start_reschedule] Unexpected error: {e}")
        return "I’m having trouble looking up your appointment right now. Please try again later."

    


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
        # Remove all characters except digits and leading +
        clean = re.sub(r"[^\d]", "", v)  # remove everything except digits

        # Allow + only if it was originally at the start
        if v.strip().startswith("+"):
            clean = "+" + clean

        # Length validation (10–15 digits ignoring +)
        digits_only = clean.lstrip("+")
        if not (10 <= len(digits_only) <= 15):
            raise ValueError("Phone number must contain 10–15 digits.")

        # Format validation (optional +, then digits)
        if not re.match(r"^\+?\d{10,15}$", clean):
            raise ValueError("Invalid phone number format.")

        return clean

@function_tool
async def start_cancel() -> str:
    """
    Start cancellation flow.
    Checks patient record and upcoming appointment.
    """
    ctx = _ctx()

    if not ctx.phone:
        return "I need your phone number to find your appointment. What’s your number?"

    try:
        with db_context():
            patient = get_patient_by_phone(ctx.phone)
            if not patient:
                return "I couldn’t find your record with this phone number."

            upcoming = get_upcoming_appointment(patient["id"])
            if not upcoming:
                return "You don’t have any upcoming appointment. Would you like to book a new one?"

            # Store selected appointment ID for safe cancel
            ctx.mode = "cancel"
            ctx.cancel_appt_id = upcoming.id
            _save(ctx)

            return f"I found your appointment on {upcoming.date} at {upcoming.time}. Would you like to cancel it?"
    except Exception as e:
        logger.exception(f"[start_cancel] Unexpected error: {e}")
        return "I’m having trouble accessing our booking system right now. Please try again later."


@function_tool
async def confirm_cancel() -> str:
    """
    Final step for canceling an appointment.
    Must only run after start_cancel(), when ctx.mode == "cancel".
    """
    ctx = _ctx()

    try:
        # 1️⃣ Ensure we're in cancel mode
        if ctx.mode != "cancel":
            return "I’m not canceling anything yet. What would you like to cancel?"

        # 2️⃣ Ensure phone exists in context
        if not ctx.phone:
            return "I need your phone number to find your appointment."

        # 3️⃣ Ensure appointment ID stored
        if not hasattr(ctx, "cancel_appt_id") or not ctx.cancel_appt_id:
            return "I couldn’t find the appointment you want to cancel."

        with db_context():
            # 4️⃣ Load appointment safely
            appt = Appointment.query.get(ctx.cancel_appt_id)
            if not appt:
                return "That appointment no longer exists."

            # Store details before delete
            date_text = appt.date
            time_text = appt.time

            # 5️⃣ Delete appointment
            deleted = delete_appointment(ctx.cancel_appt_id)
            if not deleted:
                logger.error(
                    f"[confirm_cancel] delete_appointment returned False for id={ctx.cancel_appt_id}"
                )
                return "Sorry, I couldn't cancel the appointment. Please try again."

        # 6️⃣ Cleanup context
        ctx.mode = None
        ctx.cancel_appt_id = None
        _save(ctx)

        return (
            f"Your appointment on {date_text} at {time_text} is canceled. "
            "Anything else I can help with?"
        )

    except Exception as e:
        logger.error(f"[confirm_cancel] Error: {e}")
        return "Sorry, I couldn't cancel the appointment. Please try again."



class BookingCreate(BookingBase):
    date: str = Field(..., description="Appointment date in YYYY-MM-DD format")
    time: str = Field(..., description="Appointment time in HH:MM format (24-hour)")

    @validator("date")
    def validate_date(cls, v):
        try:
            datetime.strptime(v, "%Y-%m-%d")
            if datetime.strptime(v, "%Y-%m-%d") < datetime.now():
                raise ValueError("Date cannot be in the past.")
        except ValueError:
            raise ValueError("Date must be in format YYYY-MM-DD.")
        return v

    @validator("time")
    def validate_time(cls, v, values):
        try:
            # 1) Accept both formats
            time_formats = ["%H:%M", "%I:%M %p"]

            parsed_time = None
            for fmt in time_formats:
                try:
                    parsed_time = datetime.strptime(v, fmt).time()
                    break
                except ValueError:
                    pass

            if parsed_time is None:
                raise ValueError("Time must be in 'HH:MM' or 'HH:MM AM/PM' format.")

            # 2) Parse the date (string → date object)
            date_str = values.get("date")
            if not date_str:
                return v

            appt_date = datetime.strptime(str(date_str), "%Y-%m-%d").date()

            # 3) Combine date + time
            appt_datetime = datetime.combine(appt_date, parsed_time)

            # 4) Compare with NOW
            now = datetime.now()
            if appt_datetime < now:
                raise ValueError("Selected time is in the past.")

            return v

        except Exception as e:
            raise ValueError(str(e))

