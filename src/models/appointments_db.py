from extensions import db
from datetime import datetime

class Appointment(db.Model):
    __tablename__ = "appointments"  # ✅ must have '='

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patients.id'), nullable=False)
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(20), nullable=False)
    google_event_id = db.Column(db.String(200))
    status = db.Column(db.String(50), default='Pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship back to Patient
    patient = db.relationship('Patient', backref=db.backref('appointments', lazy=True))