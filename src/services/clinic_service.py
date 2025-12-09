from datetime import datetime
from extensions import db
from src.models import Patient, Appointment
from src.services.db_context import db_context
import pytz
import logging


logger = logging.getLogger("clinic_service")


# -------------------------------
# 👤 PATIENT HELPERS
# -------------------------------

def get_patient_by_phone(phone: str):
    """Always use phone as primary key for patient identity."""
    try:
        with db_context():
            p = Patient.query.filter_by(phone=phone).first()
            if not p:
                return None
            return {"id": p.id, "name": p.name, "phone": p.phone}
    except Exception as e:
        logger.exception(f"[get_patient_by_phone] Failed for phone={phone}: {e}")
        return None


def get_or_create_patient(name: str, phone: str):
    """Create a new patient only if phone not exists."""
    try:
        with db_context():
            p = Patient.query.filter_by(phone=phone).first()

            if p:
                # Already exists — return same structure
                return {"id": p.id, "name": p.name, "phone": p.phone}

            # Create a new record
            new_p = Patient(
                name=name.strip().title(),
                phone=phone,
                created_at=datetime.utcnow()
            )
            db.session.add(new_p)
            db.session.commit()

            return {"id": new_p.id, "name": new_p.name, "phone": new_p.phone}
    except Exception as e:
        logger.exception(f"[get_or_create_patient] Failed for phone={phone}, name={name}: {e}")
        return None


def upsert_patient(name: str, phone: str, email: str | None = None, patient_id: int | None = None):
    """
    Create or update a patient record for dashboard/manual control.
    - If patient_id is provided, update that patient.
    - Otherwise, upsert by phone (phone is unique in DB).
    """
    try:
        with db_context():
            target = None

            if patient_id is not None:
                target = Patient.query.get(patient_id)

            if target is None:
                # Fallback to phone-based lookup
                target = Patient.query.filter_by(phone=phone).first()

            if target:
                # Update existing record
                target.name = name.strip().title()
                target.phone = phone
                if email is not None:
                    target.email = email
                db.session.add(target)
                db.session.commit()
                return target

            # Create a new record
            new_p = Patient(
                name=name.strip().title(),
                phone=phone,
                email=email,
                created_at=datetime.utcnow(),
            )
            db.session.add(new_p)
            db.session.commit()
            return new_p
    except Exception as e:
        logger.exception(f"[upsert_patient] Failed for patient_id={patient_id}, phone={phone}: {e}")
        return None


def delete_patient(patient_id: int) -> bool:
    """Delete a patient record safely."""
    try:
        with db_context():
            p = Patient.query.get(patient_id)
            if not p:
                return False
            db.session.delete(p)
            db.session.commit()
            return True
    except Exception as e:
        logger.exception(f"[delete_patient] Error deleting patient {patient_id}: {e}")
        return False


# -------------------------------
# 📅 APPOINTMENT HELPERS
# -------------------------------

def get_upcoming_appointment(patient_id: int):
    """Return the next upcoming appointment with proper date comparison."""
    try:
        # Use clinic timezone
        tz = pytz.timezone("Asia/Karachi")
        today = datetime.now(tz).date()   # real date object

        with db_context():
            appointments = (
                Appointment.query
                .filter(Appointment.patient_id == patient_id)
                .all()
            )

        if not appointments:
            return None

        # Convert strings to date objects safely
        parsed = []
        for a in appointments:
            try:
                appt_date = datetime.strptime(a.date, "%Y-%m-%d").date()
            except Exception:
                continue  # skip invalid rows
            if appt_date >= today:
                parsed.append((appt_date, a))

        if not parsed:
            return None

        # Get earliest upcoming
        parsed.sort(key=lambda x: x[0])
        return parsed[0][1]
    except Exception as e:
        logger.exception(f"[get_upcoming_appointment] Failed for patient_id={patient_id}: {e}")
        return None


def create_appointment(patient_id: int, date: str, time: str):
    """Create a new future appointment."""
    try:
        with db_context():
            appt = Appointment(
                patient_id=patient_id,
                date=date,
                time=time,
                status="Booked",
                created_at=datetime.utcnow(),
            )
            db.session.add(appt)
            db.session.commit()
            return appt
    except Exception as e:
        logger.exception(
            f"[create_appointment] Failed for patient_id={patient_id}, date={date}, time={time}: {e}"
        )
        return None


def reschedule_appointment(appt_id: int, new_date: str, new_time: str):
    """Safely reschedule an appointment."""
    try:
        with db_context():
            appt = Appointment.query.get(appt_id)   # Always load inside session

            if not appt:
                return None

            appt.date = new_date
            appt.time = new_time
            appt.status = "Rescheduled"

            db.session.add(appt)  # ensure tracked
            db.session.commit()

            return appt
    except Exception as e:
        logger.exception(
            f"[reschedule_appointment] Failed for appt_id={appt_id}, date={new_date}, time={new_time}: {e}"
        )
        return None


def get_booked_slots(date: str):
    """Return all booked slots for a given date."""
    try:
        with db_context():
            appointments = (
                Appointment.query
                .filter(Appointment.date == date)
                .filter(Appointment.status == "Booked")
                .all()
            )
            return [a.time for a in appointments]
    except Exception as e:
        logger.exception(f"[get_booked_slots] Failed for date={date}: {e}")
        return []

def delete_appointment(appointment_id: int) -> bool:
    """
    Delete an appointment record safely using db_context.
    Returns True if deleted, False otherwise.
    """
    try:
        with db_context():
            appt = Appointment.query.get(appointment_id)
            if not appt:
                return False

            db.session.delete(appt)
            db.session.commit()
            return True

    except Exception as e:
        logger.exception(f"[delete_appointment] Error deleting appointment {appointment_id}: {e}")
        return False


def upsert_appointment(
    *,
    appointment_id: int | None,
    patient_id: int,
    date: str,
    time: str,
    status: str | None = None,
):
    """
    Create or update an appointment for dashboard/manual control.
    - If appointment_id is provided, update that appointment.
    - Otherwise, create a new one.
    """
    try:
        with db_context():
            if appointment_id:
                appt = Appointment.query.get(appointment_id)
            else:
                appt = Appointment(
                    patient_id=patient_id,
                    date=date,
                    time=time,
                    status="Booked",
                    created_at=datetime.utcnow(),
                )

            if not appt:
                return None

            appt.patient_id = patient_id
            appt.date = date
            appt.time = time
            if status:
                appt.status = status

            db.session.add(appt)
            db.session.commit()
            return appt
    except Exception as e:
        logger.exception(
            f"[upsert_appointment] Failed for appointment_id={appointment_id}, patient_id={patient_id}: {e}"
        )
        return None


def get_dashboard_snapshot():
    """
    Aggregate data for the receptionist dashboard:
    - Today's appointments (with patient info)
    - High-level stats
    - Recent patients list
    """
    try:
        try:
            tz = pytz.timezone("Asia/Karachi")
        except Exception:
            tz = pytz.UTC

        now = datetime.now(tz)
        today_str = now.strftime("%Y-%m-%d")

        with db_context():
            # All appointments for today (ordered by time)
            todays_appointments = (
                Appointment.query
                .filter(Appointment.date == today_str)
                .order_by(Appointment.time.asc())
                .all()
            )

            # Recent patients (limit to avoid huge tables)
            recent_patients = (
                Patient.query
                .order_by(Patient.created_at.desc())
                .limit(50)
                .all()
            )

            total_patients = Patient.query.count()

            # Build appointment payload and compute status breakdown
            status_counts: dict[str, int] = {}
            today_payload = []
            for appt in todays_appointments:
                status = appt.status or "Unknown"
                status_counts[status] = status_counts.get(status, 0) + 1

                # Access relationship while session is still active to avoid DetachedInstanceError.
                patient_obj = getattr(appt, "patient", None)
                today_payload.append(
                    {
                        "id": appt.id,
                        "time": appt.time,
                        "date": appt.date,
                        "status": status,
                        "patient": {
                            "id": getattr(patient_obj, "id", None),
                            "name": getattr(patient_obj, "name", "Unknown"),
                            "phone": getattr(patient_obj, "phone", ""),
                        },
                    }
                )

            patients_payload = []
            for p in recent_patients:
                created_str = ""
                try:
                    if p.created_at:
                        created_str = p.created_at.strftime("%b %d, %Y")
                except Exception:
                    created_str = ""

                patients_payload.append(
                    {
                        "id": p.id,
                        "name": p.name,
                        "phone": p.phone,
                        "email": p.email,
                        "created_at_human": created_str,
                    }
                )

        stats = {
            "total_patients": total_patients,
            "today_total": len(today_payload),
            "today_booked": status_counts.get("Booked", 0),
            "today_rescheduled": status_counts.get("Rescheduled", 0),
            "today_pending": status_counts.get("Pending", 0),
            "today_cancelled": status_counts.get("Cancelled", 0),
            "timezone": str(tz),
            "today_label": now.strftime("%A, %b %d"),
            "as_of_human": now.strftime("%b %d, %Y %I:%M %p"),
        }

        return {
            "stats": stats,
            "today_appointments": today_payload,
            "patients": patients_payload,
        }

    except Exception as e:
        logger.exception(f"[get_dashboard_snapshot] Failed: {e}")
        # In case of failure, return safe empty structures so UI still loads.
        return {
            "stats": {
                "total_patients": 0,
                "today_total": 0,
                "today_booked": 0,
                "today_rescheduled": 0,
                "today_pending": 0,
                "today_cancelled": 0,
                "timezone": "UTC",
                "today_label": "",
                "as_of_human": "",
            },
            "today_appointments": [],
            "patients": [],
        }