<!-- 2e84d4d9-c4c5-4b69-955d-06c53c1c00a6 89f2a372-3108-40ae-9449-5d2105dd4023 -->
# Voice Agent Confirmation & Safety Plan

## Goal

Ensure the LiveKit voice agent:

- Clearly repeats and **confirms name, phone, date, and time** before booking.
- **Disallows past appointments** (past dates and earlier times today).
- Avoids common booking loopholes (missing info, double booking, duplicate patients).

## Steps

### 1. Analyse current booking flow

- Review `src/routes/livekit/tools.py` for:
- `available_slot`, `booking_appointment`, `get_date`, `start_reschedule`, `confirm_reschedule`, `start_cancel`, `confirm_cancel`, `save_name`, `save_phone`.
- How they read/write `BookingContext` and call `clinic_service` helpers.
- Review `src/routes/livekit/main.py` for the current **LLM instructions** and how tools are described (especially booking and confirmation wording).
- Review `src/services/clinic_service.py` to see how `create_appointment`, `get_booked_slots`, and `get_or_create_patient` behave (including timezone and dedupe by phone).

### 2. Add strict server-side validation for appointments

- In `clinic_service` (or a new helper), add a small validator that:
- Parses requested `date` and `time` into a concrete `datetime` in the clinic timezone.
- Returns an error if the target slot is **in the past** (date before today, or today with time earlier than now).
- Update the tool implementation that actually creates the appointment (likely `booking_appointment` / `confirm_reschedule` wrappers around `create_appointment`) to:
- Call the validator and **refuse to book** for past slots.
- If past, return a structured message (e.g. `{"ok": false, "reason": "past_time", "suggestions": [...]}`) so the LLM can ask the caller to choose another time.
- Ensure we still use `get_or_create_patient` by phone so patient records are not duplicated when the caller gives an existing number.

### 3. Enforce final confirmation before booking

- Strengthen the **LLM prompt** in `livekit/main.py`:
- Add an explicit rule: *“Before calling `booking_appointment` or `confirm_reschedule`, you MUST: 1) repeat caller name, phone, date, and time in one short sentence; 2) ask ‘Should I confirm this appointment?’ and only call the tool after the caller clearly says yes.”*
- On the tool side (`booking_appointment` in `tools.py`):
- Treat it as the **final commit** step: only execute if `BookingContext` already has `name`, `phone`, `date`, and `time` populated.
- If any are missing, return an error to the LLM indicating which field is missing rather than silently booking.
- Optionally introduce a small helper like `summarize_current_request(ctx)` that returns a short summary string; use it in tools or in the instruction examples to keep confirmations consistent.

### 4. Improve slot suggestion when a time is invalid or full

- In `available_slot` / booking tools:
- If a requested day has no free slots **or** the chosen time is invalid/past, use `get_booked_slots` and clinic working hours to compute the **next available time**.
- Return that suggestion to the LLM in a structured way (e.g. `{"ok": false, "reason": "no_slot", "next_slot": "2025-12-10 11:00"}`) so the agent can say: “That time is not available. I can offer Wednesday at 11:00. Does that work?”

### 5. Tighten edge cases and loopholes

- Prevent duplicate patients:
- Confirm that all flows that result in an appointment call `get_or_create_patient` (by phone) rather than creating `Patient` directly.
- If any tool bypasses this, refactor it to use `get_or_create_patient`.
- Ensure booking only happens once per call:
- In `BookingContext`, set a flag (e.g. `status = "booked"`) after a successful booking and have `booking_appointment` short‑circuit with a message if it’s called again.
- Double-check cancel and reschedule tools still work with the new past-time and confirmation rules.

### 6. (Optional) Surface booking state on the dashboard

- Extend the dashboard to show, for each **live call session** (already added), the current `stage` and whether the appointment is **pending confirmation** vs **booked**, so a human can see where the agent is in the flow.

If you approve this plan, I’ll implement it by updating the relevant tools, adding the validation helpers, and adjusting the LLM instructions, then we can test a couple of example calls to confirm the behavior feels right for your clinic.

### To-dos

- [ ] Analyse livekit tools, main agent instructions, and clinic_service helpers to understand current booking and confirmation flow
- [ ] Add server-side validation to block past appointments and enforce required fields before creating bookings
- [ ] Update LLM instructions and booking tools to require a spoken final confirmation of name, phone, date, and time before booking
- [ ] Enhance available_slot/booking logic to suggest next available time when requested slot is past or fully booked
- [ ] Audit tools for duplicate patient creation, repeat booking, and ensure consistent use of get_or_create_patient