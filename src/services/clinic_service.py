from datetime import datetime
from extensions import db
from src.models import Patient, Appointment
from src.services.db_context import db_context
import pytz


# -------------------------------
# 👤 PATIENT HELPERS
# -------------------------------

def get_patient_by_phone(phone: str):
    """Always use phone as primary key for patient identity."""
    with db_context():
        p = Patient.query.filter_by(phone=phone).first()
        if not p:
            return None
        return {"id": p.id, "name": p.name, "phone": p.phone}


def get_or_create_patient(name: str, phone: str):
    """Create a new patient only if phone not exists."""
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


# -------------------------------
# 📅 APPOINTMENT HELPERS
# -------------------------------

def get_upcoming_appointment(patient_id: int):
    """Return the next upcoming appointment with proper date comparison."""
    
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
        except:
            continue  # skip invalid rows
        if appt_date >= today:
            parsed.append((appt_date, a))

    if not parsed:
        return None

    # Get earliest upcoming
    parsed.sort(key=lambda x: x[0])
    return parsed[0][1]


def create_appointment(patient_id: int, date: str, time: str):
    """Create a new future appointment."""
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

def reschedule_appointment(appt_id: int, new_date: str, new_time: str):
    """Safely reschedule an appointment."""
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


def get_booked_slots(date: str):
    """Return all booked slots for a given date."""
    with db_context():
        appointments = (
            Appointment.query
            .filter(Appointment.date == date)
            .filter(Appointment.status == "Booked")
            .all()
        )
        return [a.time for a in appointments]