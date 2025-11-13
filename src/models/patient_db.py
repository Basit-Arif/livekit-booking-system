from extensions import db, migrate # ✅ note: correct spelling 'extensions'

class Patient(db.Model):
    __tablename__ = "patients"  # ✅ single underscore, not triple

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, server_default=db.func.now())

