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
    caller_id = CURRENT_PARTICIPANT.get()
    if not caller_id:
        return

    # Load old context (if it exists)
    old = load_context(caller_id)

    if not old:
        # No existing context → simply save entire object
        save_context(caller_id, ctx)
        logger.info(f"[Redis] Saved NEW context for {caller_id}: {ctx}")
        return

    # Convert dataclasses to dicts
    old_dict = asdict(old)
    new_dict = asdict(ctx)

    # Merge dictionaries: only update non-None values
    for key, value in new_dict.items():
        if value is not None:
            old_dict[key] = value

    # Create a new merged BookingContext object
    merged = BookingContext(**old_dict)

    save_context(caller_id, merged)
    logger.info(f"[Redis] Saved MERGED context for {caller_id}: {merged}")

# 🧹 Clear context from Redis
def _clear():
    pid = CURRENT_PARTICIPANT.get(None)
    if pid:
        clear_context(pid)
        logger.info(f"[Redis] Cleared context for {pid}")