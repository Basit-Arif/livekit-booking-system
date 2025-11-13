import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextvars import ContextVar
from livekit.agents import Agent, AgentSession, JobContext
from livekit.plugins import deepgram, openai,silero,cartesia
from src.app_factory import create_app
from src.services.clinic_service import get_or_create_patient, create_appointment
from src.routes.livekit.tools import save_name,save_phone,available_slot,booking_appointment,get_date
from src.services.redis_service import BookingContext, load_context, save_context, clear_context,r,save_caller_profile,_caller_key,load_caller_profile,CallerProfile,load_context_if_exists,hydrate_context

from datetime import datetime
from src.services.context_manager import _ctx, _save, _clear, CURRENT_PARTICIPANT
import re



load_dotenv()
logger = logging.getLogger("telephony-agent")
flask_app = create_app()



 # ---------------------------Pydantic ---------------------------#
def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    # Extract digits only (so “sip_+923001234567” → “923001234567”)
    digits = re.sub(r'\D', '', raw)
    return digits[-11:] if len(digits) >= 10 else None


# ---------------------------- Entry ---------------------------- #

async def entrypoint(ctx: JobContext):
    await ctx.connect()
    pong = r.ping()
    logger.info(f"🔌 Redis Connected: {pong}")

    participant = await ctx.wait_for_participant()
    caller_id = participant.identity
    token = CURRENT_PARTICIPANT.set(caller_id)

    logger.info(f"📞 Incoming call from: {caller_id}")

    # Step 1️⃣ — Try to get caller phone number (from SIP or LiveKit identity)
    caller_phone = None
    if hasattr(participant, "metadata") and participant.metadata:
        caller_phone = participant.metadata.get("phone")
    if not caller_phone:
        caller_phone = caller_id  # fallback if not available

    logger.info(f"📞 Caller Phone Detected: {caller_phone}")

    # Step 2️⃣ — Decide which context to load (Session → Profile → Fresh)
    redis_ctx = load_context_if_exists(caller_id)
    if redis_ctx:
        logger.info("[Memory] 🔁 Resumed active BookingSession (within 10 min)")
    else:
        redis_ctx = hydrate_context(caller_id, normalize_phone(caller_phone))
        logger.info("[Memory] 🧠 Hydrated from CallerProfile or DB")

    remembered = bool(redis_ctx and (redis_ctx.name or redis_ctx.date or redis_ctx.time))
    memory_text = (
        f"The caller previously gave the name {redis_ctx.name or 'unknown'}, "
        f"phone {redis_ctx.phone or 'unknown'}, and discussed an appointment for "
        f"{redis_ctx.date or 'unspecified'} at {redis_ctx.time or 'unspecified'}. "
        "Continue as if you remember them naturally."
    ) if remembered else ""

    # Step 3️⃣ — Create AI Agent
    agent = Agent(
        instructions=f"""
            You are an **AI receptionist** for Shifa Clinic.
            Your goal is to **book, confirm, or reschedule appointments** naturally.

            Current memory: {memory_text}

            ## Behavior
            - Greet warmly based on time of day.
            - Confirm info clearly before saving.
            - Never repeat phone digits unless confirming.
            - Engage naturally while tools execute ("Just a second, I’m checking that for you...").

            ## Tools
            1. `save_name(name)` when the user says their name.
            2. `save_phone(phone)` when the user says or repeats digits.
            3. `available_slot()` when they mention time or say morning/afternoon.
            4. `booking_appointment()` to finalize bookings.
            5. `get_date()` to detect date info if needed.

            ## Voice
            - Keep replies short (under 12 words).
            - Use fillers naturally: “Just a moment...”, “Let me check...”.
            - End with warmth: “You’re all set! Have a great day.”
            ### Instruction
            When the caller pauses briefly or finishes a phrase (even a short one),
                respond immediately. You don’t need to wait for long silence.
        """,
        tools=[save_name, save_phone, available_slot, booking_appointment, get_date],
    )

    # Step 4️⃣ — Configure Agent Session
    session = AgentSession[BookingContext](
        userdata=redis_ctx,
        vad=silero.VAD.load(min_speech_duration=0.25),
        stt=deepgram.STT(model="nova-3", language="multi",interim_results=True),
        llm=openai.LLM(model="gpt-4o-mini", temperature=0.7),
        tts=openai.TTS(voice="alloy"),
    )

    await session.start(agent=agent, room=ctx.room)

    # Step 5️⃣ — Personalized Greeting
    if remembered and redis_ctx.name:
        greeting = f"Welcome back {redis_ctx.name}! Should I continue with your appointment for {redis_ctx.date or 'soon'}?"
    else:
        hour = datetime.now().hour
        greeting = (
            "Good morning! " if hour < 12 else
            "Good afternoon! " if hour < 18 else
            "Good evening! "
        ) + "Thank you for calling Shifa Clinic. How can I help you today?"

    await session.generate_reply(instructions=greeting)

    # Step 6️⃣ — Persist memory safely
    try:
        if redis_ctx and any([redis_ctx.name, redis_ctx.phone, redis_ctx.date, redis_ctx.time]):
            save_context(caller_id, redis_ctx)
            save_caller_profile(
                CallerProfile(
                    name=redis_ctx.name,
                    phone=redis_ctx.phone,
                    last_appointment={"date": redis_ctx.date, "time": redis_ctx.time},
                )
            )
            logger.info(f"[Redis] 💾 Updated memory for {caller_id}: {redis_ctx}")
    finally:
        CURRENT_PARTICIPANT.reset(token)