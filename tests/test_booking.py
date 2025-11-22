from datetime import datetime, timedelta
import pytest
import asyncio

from flask import Flask

from src.app_factory import create_app
from extensions import db
from src.models import Patient, Appointment


@pytest.fixture
def app() -> Flask:
    app = create_app()
    # Use sqlite file for stability across threads
    app.config.update(
        SQLALCHEMY_DATABASE_URI="sqlite:///test_clinic.db",
        TESTING=True,
    )
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def app_ctx(app: Flask):
    with app.app_context():
        yield


def _insert_patient_and_appt(name: str, phone: str, date: str, time: str):
    patient = Patient(name=name, phone=phone)
    db.session.add(patient)
    db.session.commit()
    appt = Appointment(
        patient_id=patient.id,
        date=date,
        time=time,
        status="Booked",
        created_at=datetime.utcnow(),
    )
    db.session.add(appt)
    db.session.commit()
    return patient, appt


def test_books_new_when_no_upcoming(app, app_ctx, monkeypatch):
    from src.routes.livekit import tools as tl
    from src.services.redis_service import BookingContext
    from src.services import db_context as dbc
    # Route db_context to the test app
    monkeypatch.setattr(dbc, "flask_app", app)

    # Provide booking context with no prior appointments
    ctx = BookingContext(
        name="Test User",
        phone="15551234567",
        date=(datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d"),
        suggested_slots=["10:00 AM"],
    )
    monkeypatch.setattr(tl, "_ctx", lambda: ctx)
    monkeypatch.setattr(tl, "_save", lambda _ctx: None)

    # Call booking
    result = asyncio.run(tl.booking_appointment())
    assert "booked for" in result.lower() or "has been booked" in result.lower()

    # DB should contain the new appointment
    patient = Patient.query.filter_by(phone="15551234567").first()
    assert patient is not None
    appt = Appointment.query.filter_by(patient_id=patient.id, date=ctx.date).first()
    assert appt is not None


def test_upcoming_asks_reschedule(app, app_ctx, monkeypatch):
    from src.routes.livekit import tools as tl
    from src.services.redis_service import BookingContext
    from src.services import db_context as dbc
    # Route db_context to the test app
    monkeypatch.setattr(dbc, "flask_app", app)

    # Seed existing upcoming appointment
    today = datetime.utcnow().date()
    existing_date = (today + timedelta(days=1)).strftime("%Y-%m-%d")
    _insert_patient_and_appt("Alice", "15557654321", existing_date, "9:30 AM")

    # Provide context proposing a different slot
    new_date = (today + timedelta(days=2)).strftime("%Y-%m-%d")
    ctx = BookingContext(
        name="Alice",
        phone="15557654321",
        date=new_date,
        suggested_slots=["10:00 AM"],
    )
    monkeypatch.setattr(tl, "_ctx", lambda: ctx)
    monkeypatch.setattr(tl, "_save", lambda _ctx: None)

    # Call booking; should ask to move instead of booking immediately
    result = asyncio.run(tl.booking_appointment())
    assert "should i move" in result.lower() or "would you like to reschedule" in result.lower()


