# src/routes/livekit/context_manager.py

import logging
from contextvars import ContextVar
from datetime import datetime
from dataclasses import asdict
from src.services.redis_service import save_context, load_context, clear_context,BookingContext


logger = logging.getLogger(__name__)

# 🧠 Tracks which participant (caller) is active right now
CURRENT_PARTICIPANT: ContextVar[str] = ContextVar("participant_id")

# 🧩 Get context from Redis or create new one
def _ctx() -> BookingContext:
    pid = CURRENT_PARTICIPANT.get(None)
    if not pid:
        logger.warning("Context accessed before participant set.")
        return BookingContext()
    return load_context(pid) or BookingContext()

# 💾 Save context back to Redis
def _save(ctx: BookingContext):
    pid = CURRENT_PARTICIPANT.get(None)
    if not pid:
        return
    save_context(pid, ctx)
    logger.info(f"[Redis] Saved context for {pid}: {ctx}")

# 🧹 Clear context from Redis
def _clear():
    pid = CURRENT_PARTICIPANT.get(None)
    if pid:
        clear_context(pid)
        logger.info(f"[Redis] Cleared context for {pid}")