import logging
from datetime import datetime, timedelta
from dotenv import load_dotenv
from contextvars import ContextVar
from livekit.agents import Agent, AgentSession, JobContext

from livekit.plugins.turn_detector.multilingual import MultilingualModel
from livekit.plugins import deepgram, openai,silero,cartesia
from src.app_factory import create_app
from src.services.clinic_service import get_or_create_patient, create_appointment
from src.routes.livekit.tools import save_name,save_phone,available_slot,booking_appointment,get_date,end_call,update_caller_profile,start_reschedule,confirm_reschedule
from src.services.redis_service import BookingContext, load_context, save_context, clear_context,r,save_caller_profile,_caller_key,load_caller_profile,CallerProfile,load_context_if_exists,hydrate_context,upsert_caller_profile
import json
from datetime import datetime
from src.services.context_manager import _ctx, _save, _clear, CURRENT_PARTICIPANT
import re
from latency_tracker import LatencyTracker
from logging_setup import logger


lt = LatencyTracker()


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

    # ───────────────────────────────────────────────
    # 0️⃣  CONNECT TO REDIS
    # ───────────────────────────────────────────────
    try:
        pong = r.ping()
        logger.info(f"🔌 Redis Connected: {pong}")
    except Exception as e:
        logger.error(f"❌ Redis Connection Failed: {e}")

    # ───────────────────────────────────────────────
    # 1️⃣  WAIT FOR CALLER + SET PARTICIPANT
    # ───────────────────────────────────────────────
    participant = await ctx.wait_for_participant()
    caller_id = participant.identity
    token = CURRENT_PARTICIPANT.set(caller_id)

    logger.info(f"📞 Incoming call from: {caller_id}")

    # ───────────────────────────────────────────────
    # 2️⃣  GET CALLER PHONE/NAME FROM METADATA
    # ───────────────────────────────────────────────
    caller_phone = None
    caller_name = None

    if hasattr(participant, "metadata") and participant.metadata:
        meta = participant.metadata
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except:
                meta = {}
        if isinstance(meta, dict):
            caller_phone = meta.get("phone")
            caller_name = meta.get("name")

    if not caller_phone:
        caller_phone = caller_id  # fallback

    normalized_phone = normalize_phone(caller_phone)
    logger.info(f"📞 Caller Phone Detected (normalized): {normalized_phone}")

    # ───────────────────────────────────────────────
    # 3️⃣  ALWAYS RESET SESSION CONTEXT FOR NEW CALL
    #     (This stops old memory, old dates, old states)
    # ───────────────────────────────────────────────
    # delete_context(caller_id)
    redis_ctx = BookingContext()

    # ───────────────────────────────────────────────
    # 4️⃣  LOAD CALLER PROFILE (PERMANENT MEMORY)
    #     Do NOT load old session memory.
    # ───────────────────────────────────────────────
    if normalized_phone:
        try:
            # hydrate_context loads CallerProfile AND builds BookingContext
            redis_ctx = hydrate_context(caller_id, normalized_phone)

            # Profile already loaded inside hydrate_context → reuse for greeting
            profile = load_caller_profile(normalized_phone)
            caller_name = profile.name

            logger.info(f"[Hydrate] Profile + Session loaded for {normalized_phone}")

        except Exception as e:
            logger.error(f"[Hydrate] Failed: {e}")
            redis_ctx = BookingContext(phone=normalized_phone)

    else:
    # No phone → force ask_phone stage
        redis_ctx = hydrate_context(caller_id, None)
        caller_name = None
    # ───────────────────────────────────────────────
    # 5️⃣  SET UP AGENT (NO MEMORY LEAKS)
    # ───────────────────────────────────────────────
    agent = Agent(
        instructions=f"""
        You are Shifa Clinic’s AI Receptionist, answering real-time phone calls.
Your job is to help callers book, confirm, or reschedule appointments.
Speak naturally, briefly, and professionally—like an experienced clinic receptionist.

────────────────────────
### CORE BEHAVIOR
────────────────────────
• Treat every call as new.  
  Use ONLY caller name (if spoken), phone (if spoken), and information from THIS call.

• Respond in under **8 words**.  
  One short sentence. One question at a time.

• Always confirm what the caller said before asking the next step.

• NEVER reveal internal logic, tools, memory, or reasoning.

• Stay calm, polite, warm, and concise at all times.

────────────────────────
### ALLOWED TOOL USAGE
────────────────────────
You may call:
- save_name(name)
- save_phone(phone)
- available_slot(day?, date?, time?)
- booking_appointment(time)
- get_date()
- update_caller_profile(name?, phone?)
- start_reschedule()
- confirm_reschedule(time)
- end_call()  ← ONLY when caller clearly ends the conversation

Tool guidelines:
• If caller says a name → call save_name immediately.  
• If caller says phone digits → call save_phone immediately.  
  If unclear digits, ask: “Repeat the number slowly?”

• If caller mentions timing (morning, 3pm, evening, after 2) → call available_slot.  
• If caller mentions vague dates (“next Monday”) → call get_date.  
• Call booking_appointment ONLY when BOTH date and time are known.  
• Caller corrects name/phone → update_caller_profile.

After a booking or reschedule:
Ask: **“Anything else I can help with?”**

────────────────────────
### RESCHEDULE FLOW
────────────────────────
If caller says “change”, “shift”, “move”, “reschedule”:
1. Call start_reschedule()
2. Ask for new date
3. Ask for new time
4. When BOTH are known → call confirm_reschedule()
5. THEN ask: “Anything else I can help with?”

Do NOT call confirm_reschedule early.

────────────────────────
### SAFETY (NO ACCIDENTAL END CALLS)
────────────────────────
You MUST NOT call end_call() unless the caller clearly says a goodbye phrase.

Valid goodbye triggers (ONLY these):
- “bye”
- “goodbye”
- “that's it”
- “nothing else”
- “no, I’m done”
- “thank you, that’s all”
- “you can end the call”
- “end the call”
- “hang up”

The following MUST NOT trigger end_call():
• silence  
• background noise  
• “hello?”  
• confusion  
• repeating themselves  
• unclear phrases  
• “no” by itself  
• “no, I want morning time”  
• “no, tell me again”  

If the caller says “hello?” reply:
→ **“I’m here. How can I help?”**

────────────────────────
### CONVERSATION STYLE
────────────────────────
• Sound human and warm.  
• Keep every response short.  
• Do NOT output paragraphs, lists, disclaimers, or explanations.  
• Ask only for information you genuinely need.  
• Never ask for info you already have.  
• After ANY tool result, reply with one short natural confirmation.

────────────────────────
### FINAL REMINDER
────────────────────────
You are the first point of contact for Shifa Clinic.
Be warm. Be efficient. Be human.

""",
        tools=[
            save_name, save_phone, available_slot,
            booking_appointment, get_date, end_call,
            update_caller_profile, start_reschedule, confirm_reschedule
        ],
    )

    # ───────────────────────────────────────────────
    # 6️⃣  CREATE AGENT SESSION
    # ───────────────────────────────────────────────
    session = AgentSession[BookingContext](
        userdata=redis_ctx,
        turn_detection=MultilingualModel(),
        stt=deepgram.STT(model="nova-3", language="multi", interim_results=True),
        llm=openai.LLM(model="gpt-4o-mini", temperature=0.7),
        tts=openai.TTS(voice="alloy"),
    )


    await session.start(agent=agent, room=ctx.room)
    @session.on("metrics_collected")
    def on_metrics(evt):
        metrics = evt.metrics

        logger.info({
            "event": "metrics",
            "type": metrics.__class__.__name__,
            "data": metrics.dict()
        })
    

    # @session.on("function_tools_executed")
    # def on_tools_executed(evt):
    #     logs = []

    #     for call, output in evt.zipped():
    #         logs.append({
    #             "tool_name": call.name,
    #             # "arguments": call.args,
    #             # "output": output.result
    #         })

        # logger.info({
        #     "event": "tools_executed",
        #     # "session_id": session.session_id,
        #     "tools": logs
        # })

    # ───────────────────────────────────────────────
    # 7️⃣  CLEAN GREETING (NO OLD MEMORY ANYMORE)
    # ───────────────────────────────────────────────
    hour = datetime.now().hour
    greeting = (
        "Good morning! " if hour < 12 else
        "Good afternoon! " if hour < 18 else
        "Good evening! "
    )

    if redis_ctx.name:
        greeting += f"Hi {redis_ctx.name}, how can I help you today?"
    else:
        greeting += "Thank you for calling Shifa Clinic. How can I help you today?"

    await session.generate_reply(instructions=greeting)

    # ───────────────────────────────────────────────
    # 8️⃣  CLEAN EXIT (NO SAVING SESSION MEMORY HERE)
    #     All saving happens INSIDE tools only.
    # ───────────────────────────────────────────────
    CURRENT_PARTICIPANT.reset(token)