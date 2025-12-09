from flask import Blueprint, render_template, request, redirect, url_for


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/", methods=["GET"])
@dashboard_bp.route("/dashboard", methods=["GET"])
def dashboard_home():
    """
    Receptionist dashboard showing today's appointments,
    high-level overview, and recent patients.
    """
    # Local import to avoid circular dependency during app startup.
    from src.services.clinic_service import get_dashboard_snapshot
    from src.services.redis_service import list_active_sessions

    context = get_dashboard_snapshot()
    context["live_sessions"] = list_active_sessions()
    return render_template("dashboard.html", active_page="overview", **context)


@dashboard_bp.route("/appointments", methods=["GET"])
def appointments_page():
    """
    Focused appointments view (same layout, different active tab).
    """
    from src.services.clinic_service import get_dashboard_snapshot
    from src.services.redis_service import list_active_sessions

    context = get_dashboard_snapshot()
    context["live_sessions"] = list_active_sessions()
    return render_template("dashboard.html", active_page="appointments", **context)


@dashboard_bp.route("/patients", methods=["GET"])
def patients_page():
    """
    Focused patients view (same layout, different active tab).
    """
    from src.services.clinic_service import get_dashboard_snapshot
    from src.services.redis_service import list_active_sessions

    context = get_dashboard_snapshot()
    context["live_sessions"] = list_active_sessions()
    return render_template("dashboard.html", active_page="patients", **context)


@dashboard_bp.route("/appointments/save", methods=["POST"])
def save_appointment():
    """
    Create or update an appointment from the dashboard form.
    """
    from src.services.clinic_service import upsert_appointment  # local import to avoid cycles

    appt_id_raw = request.form.get("appointment_id") or None
    patient_id_raw = request.form.get("patient_id") or None
    date = (request.form.get("date") or "").strip()
    time = (request.form.get("time") or "").strip()
    status = (request.form.get("status") or "").strip() or None

    appointment_id = int(appt_id_raw) if appt_id_raw else None
    patient_id = int(patient_id_raw) if patient_id_raw else None

    if patient_id and date and time:
        upsert_appointment(
            appointment_id=appointment_id,
            patient_id=patient_id,
            date=date,
            time=time,
            status=status,
        )

    return redirect(url_for("dashboard.dashboard_home"))


@dashboard_bp.route("/appointments/<int:appointment_id>/delete", methods=["POST"])
def delete_appointment_route(appointment_id: int):
    """
    Delete an appointment from the dashboard.
    """
    from src.services.clinic_service import delete_appointment  # local import to avoid cycles

    delete_appointment(appointment_id)
    return redirect(url_for("dashboard.dashboard_home"))


@dashboard_bp.route("/patients/save", methods=["POST"])
def save_patient():
    """
    Create or update a patient from the dashboard form.
    """
    from src.services.clinic_service import upsert_patient  # local import to avoid cycles

    patient_id_raw = request.form.get("patient_id") or None
    name = (request.form.get("name") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    email = (request.form.get("email") or "").strip() or None

    patient_id = int(patient_id_raw) if patient_id_raw else None

    if name and phone:
        upsert_patient(name=name, phone=phone, email=email, patient_id=patient_id)

    return redirect(url_for("dashboard.dashboard_home"))


@dashboard_bp.route("/patients/<int:patient_id>/delete", methods=["POST"])
def delete_patient_route(patient_id: int):
    """
    Delete a patient from the dashboard.
    """
    from src.services.clinic_service import delete_patient  # local import to avoid cycles

    delete_patient(patient_id)
    return redirect(url_for("dashboard.dashboard_home"))


