from extensions import db
from src.models import Patient, Appointment
from datetime import datetime
from src.services.db_context import db_context

def get_or_create_patient(name: str, phone: str = None, email: str = None):
    """Find or create a patient. Always return dict."""
    if not name:
        raise ValueError("Patient name is required.")

    with db_context():
        patient = Patient.query.filter_by(name=name).first()
        if not patient:
            patient = Patient(
                name=name.strip().title(),
                phone=phone or "",
                email=email or "",
                created_at=datetime.utcnow()
            )
            db.session.add(patient)
            db.session.commit()

        return {
            "id": patient.id,
            "name": patient.name,
            "phone": patient.phone,
            "email": patient.email
        }


def get_patient_by_phone(phone: str):
    with db_context():
        patient = Patient.query.filter_by(phone=phone).first()
        if not patient:
            return None
        return {
            "id": patient.id,
            "name": patient.name,
            "phone": patient.phone,
            "email": patient.email,
        }
# -------------------------------
# 📅 APPOINTMENT FUNCTIONS
# -------------------------------

def create_appointment(patient_id: int, date: str, time: str):
    """Create a new appointment for a patient."""
    if not all([patient_id, date, time]):
        raise ValueError("Missing required fields for appointment creation.")

    with db_context():
        appointment = Appointment(
            patient_id=patient_id,
            date=date,
            time=time,
            status="Booked",
            created_at=datetime.utcnow()
        )
        db.session.add(appointment)
        db.session.commit()
        return appointment


def find_appointments_by_name(name: str):
    """Find all appointments for a given patient name."""
    with db_context():
        patient = Patient.query.filter_by(name=name).first()
        if not patient:
            return []
        return (
            Appointment.query
            .filter_by(patient_id=patient.id)
            .order_by(Appointment.date)
            .all()
        )


def reschedule_appointment(name: str, new_date: str, new_time: str):
    """Reschedule the latest appointment for a patient."""
    with db_context():
        patient = Patient.query.filter_by(name=name).first()
        if not patient:
            return None

        latest_appointment = (
            Appointment.query
            .filter_by(patient_id=patient.id)
            .order_by(Appointment.created_at.desc())
            .first()
        )

        if latest_appointment:
            latest_appointment.date = new_date
            latest_appointment.time = new_time
            latest_appointment.status = "Rescheduled"
            db.session.commit()
            return latest_appointment

        return None


def list_all_appointments():
    """Return all appointments (for admin or dashboard)."""
    with db_context():
        return Appointment.query.order_by(Appointment.date).all()