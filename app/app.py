import io
import csv
import datetime
import sqlite3
from pathlib import Path

import cv2
import face_recognition
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

from db import (
    add_student, get_students, log_attendance, get_attendance, DB_PATH,
    get_attendance_stats, get_distinct_class_sections, get_distinct_subjects,
    get_session_count,
)
from db_extra import add_user_raw, get_user_by_username, load_settings, save_settings
from face_engine import (
    bytes_to_ndarray, compute_encodings_from_bgr, compute_boxes_and_encodings_from_bgr,
    average_encoding, match_encoding, check_liveness,
)
import alerts
import bulk_import

app = Flask(__name__, template_folder="templates", static_folder="static")

# ---------------------------------------------------------------------------
# Secret key
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Secret key — auto-generated and persisted on first run so sessions are
# secure by default, even though data/secret.key is gitignored (as it should be).
# ---------------------------------------------------------------------------
import secrets as _secrets

_SECRET_KEY_PATH = Path(__file__).resolve().parent.parent / "data" / "secret.key"
try:
    _SECRET_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    if _SECRET_KEY_PATH.exists():
        app.secret_key = _SECRET_KEY_PATH.read_text(encoding="utf-8").strip()
    else:
        app.secret_key = ""
    if not app.secret_key:
        app.secret_key = _secrets.token_hex(32)
        _SECRET_KEY_PATH.write_text(app.secret_key, encoding="utf-8")
except Exception:
    # Filesystem is read-only or otherwise unavailable (e.g. some restricted hosts) —
    # fall back to a random in-memory key. Sessions won't survive a process restart,
    # but this is still cryptographically better than a static hardcoded string.
    app.secret_key = _secrets.token_hex(32)

# ---------------------------------------------------------------------------
# Flask-Login setup
# ---------------------------------------------------------------------------
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login_page"
login_manager.login_message = "Please log in to continue."
login_manager.login_message_category = "warning"


class User(UserMixin):
    def __init__(self, id_, username, role):
        self.id = id_
        self.username = username
        self.role = role


@login_manager.user_loader
def load_user(user_id):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT id, username, role FROM users WHERE id = ?", (int(user_id),))
            r = c.fetchone()
            if not r:
                return None
            return User(r[0], r[1], r[2])
    except Exception:
        return None


# Ensure the default admin account exists (first run only).
try:
    if not get_user_by_username("admin"):
        add_user_raw("admin", generate_password_hash("admin"), role="admin")
except Exception:
    pass


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "GET":
        if session.get("user"):
            return redirect(url_for("index"))
        return render_template("login.html", hide_nav=True)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()

    if not username or not password:
        return render_template("login.html", hide_nav=True, error="Please enter both username and password.", username=username)

    user = get_user_by_username(username)
    if not user or not check_password_hash(user["password_hash"], password):
        return render_template("login.html", hide_nav=True, error="Invalid username or password.", username=username)

    user_obj = User(user["id"], user["username"], user["role"])
    login_user(user_obj)
    session["user"] = {"id": user["id"], "username": user["username"], "role": user["role"]}
    return redirect(url_for("index"))


@app.route("/logout")
@login_required
def logout():
    session.pop("user", None)
    logout_user()
    return redirect(url_for("login_page"))


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "GET":
        return render_template("change_password.html")

    current = request.form.get("current_password", "").strip()
    new = request.form.get("new_password", "").strip()
    confirm = request.form.get("confirm_password", "").strip()

    if not (current and new and confirm):
        return render_template("change_password.html", error="Please fill all fields.")
    if len(new) < 4:
        return render_template("change_password.html", error="New password must be at least 4 characters.")
    if new != confirm:
        return render_template("change_password.html", error="New passwords do not match.")

    user = get_user_by_username(current_user.username)
    if not user or not check_password_hash(user["password_hash"], current):
        return render_template("change_password.html", error="Current password is incorrect.")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(new), user["id"]))
            conn.commit()
    except Exception:
        return render_template("change_password.html", error="Could not update password. Please try again.")

    return render_template("change_password.html", success="Password changed successfully.")


@app.route("/account", methods=["GET", "POST"])
@login_required
def account_settings():
    """Lets the logged-in user change their own display username."""
    if request.method == "GET":
        return render_template("account.html", current_username=current_user.username)

    new_username = request.form.get("new_username", "").strip()
    current_password = request.form.get("current_password", "").strip()

    if not new_username or not current_password:
        return render_template("account.html", current_username=current_user.username,
                                error="Please fill all fields.")

    user = get_user_by_username(current_user.username)
    if not user or not check_password_hash(user["password_hash"], current_password):
        return render_template("account.html", current_username=current_user.username,
                                error="Current password is incorrect.")

    if get_user_by_username(new_username) and new_username != current_user.username:
        return render_template("account.html", current_username=current_user.username,
                                error=f"Username '{new_username}' is already taken.")

    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("UPDATE users SET username = ? WHERE id = ?", (new_username, user["id"]))
            conn.commit()
    except sqlite3.IntegrityError:
        return render_template("account.html", current_username=current_user.username,
                                error="That username is already taken.")
    except Exception:
        return render_template("account.html", current_username=current_user.username,
                                error="Could not update username. Please try again.")

    # Refresh session so nav bar / current_user reflect the new username immediately
    session["user"]["username"] = new_username
    logout_user()
    login_user(User(user["id"], new_username, user["role"]))
    return render_template("account.html", current_username=new_username, success="Username updated successfully.")


# ---------------------------------------------------------------------------
# Page routes (protected)
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def index():
    return render_template("index.html")


@app.route("/enroll")
@login_required
def enroll_page():
    return render_template("enroll.html")


@app.route("/attendance")
@login_required
def attendance_page():
    return render_template("attendance.html")


@app.route("/reports")
@login_required
def reports_page():
    return render_template("reports.html")


@app.route("/dashboard")
@login_required
def dashboard_page():
    return render_template("dashboard.html")


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings_page():
    if current_user.role != "admin":
        return redirect(url_for("index"))

    settings = load_settings()
    if request.method == "POST":
        try:
            t = float(request.form.get("tolerance", settings.get("tolerance", 0.45)))
            settings["tolerance"] = max(0.2, min(0.8, t))

            threshold = float(request.form.get("attendance_alert_threshold", settings.get("attendance_alert_threshold", 75)))
            settings["attendance_alert_threshold"] = max(0, min(100, threshold))

            settings["liveness_enabled"] = request.form.get("liveness_enabled") == "on"

            settings["smtp_host"] = request.form.get("smtp_host", "").strip()
            settings["smtp_port"] = int(request.form.get("smtp_port", 587) or 587)
            settings["smtp_username"] = request.form.get("smtp_username", "").strip()
            new_pw = request.form.get("smtp_password", "").strip()
            if new_pw:
                settings["smtp_password"] = new_pw
            settings["smtp_from"] = request.form.get("smtp_from", "").strip()
            settings["smtp_use_tls"] = request.form.get("smtp_use_tls") == "on"

            settings["last_updated"] = datetime.datetime.utcnow().isoformat()
            save_settings(settings)
        except Exception:
            pass
        return redirect(url_for("settings_page"))
    return render_template("settings.html", settings=settings)


@app.route("/bulk_import", methods=["GET", "POST"])
@login_required
def bulk_import_page():
    if current_user.role != "admin":
        return redirect(url_for("index"))

    if request.method == "GET":
        return render_template("bulk_import.html", results=None)

    zip_file = request.files.get("zip_file")
    mapping_file = request.files.get("mapping_csv")
    if not zip_file:
        return render_template("bulk_import.html", results=None, error="Please choose a ZIP file of photos.")

    mapping_bytes = mapping_file.read() if mapping_file and mapping_file.filename else None
    results = bulk_import.process_zip(zip_file.read(), mapping_bytes)
    added = sum(1 for r in results if r["status"] == "added")
    return render_template("bulk_import.html", results=results, added_count=added, total_count=len(results))


# ---------------------------------------------------------------------------
# API routes (protected)
# ---------------------------------------------------------------------------
@app.post("/api/enroll")
@login_required
def api_enroll():
    name = request.form.get("name", "").strip()
    roll = request.form.get("roll", "").strip()
    class_section = request.form.get("class_section", "").strip()
    email = request.form.get("email", "").strip() or None
    if not (name and roll and class_section):
        return jsonify({"ok": False, "error": "Missing fields"}), 400

    files = request.files.getlist("images")
    encs = []
    for f in files:
        img = bytes_to_ndarray(f.read())
        if img is None:
            continue
        enc = compute_encodings_from_bgr(img)
        if enc:
            encs.extend(enc)
    if not encs:
        return jsonify({"ok": False, "error": "No face detected in the captured samples"}), 400

    try:
        avg = average_encoding(encs)
        student_id = add_student(name, roll, class_section, avg.tolist(), email=email)
    except sqlite3.IntegrityError:
        return jsonify({"ok": False, "error": f"Roll number '{roll}' already exists"}), 400

    return jsonify({"ok": True, "student_id": student_id})


@app.post("/api/recognize")
@login_required
def api_recognize():
    subject = request.form.get("subject")
    class_section = request.form.get("class_section")
    device_id = request.form.get("device_id")
    f = request.files.get("image")
    f2 = request.files.get("image2")
    if not f:
        return jsonify({"ok": False, "error": "No image"}), 400

    img = bytes_to_ndarray(f.read())
    if img is None:
        return jsonify({"ok": False, "error": "Invalid image"}), 400

    img2 = bytes_to_ndarray(f2.read()) if f2 else None

    boxes, encs = compute_boxes_and_encodings_from_bgr(img)
    if not encs:
        return jsonify({"ok": True, "results": [], "note": "no_face_detected"})

    students = get_students()
    known = [s["encoding"] for s in students]
    settings = load_settings()
    tolerance = float(settings.get("tolerance", 0.45))
    liveness_enabled = bool(settings.get("liveness_enabled", True))

    results = []
    for box, e in zip(boxes, encs):
        live = check_liveness(img, img2, box) if (liveness_enabled and img2 is not None) else None
        if live is False:
            results.append({"match": False, "reason": "liveness_failed", "distance": None})
            continue

        idx, dist = match_encoding(e, known, tolerance=tolerance)
        if idx != -1:
            sid = students[idx]["id"]
            log_attendance(sid, subject=subject, class_section=class_section, device_id=device_id)
            results.append({
                "match": True, "student_id": sid, "name": students[idx]["name"],
                "roll": students[idx]["roll"], "distance": dist,
            })
        else:
            results.append({"match": False, "distance": dist})
    return jsonify({"ok": True, "results": results})


@app.post("/api/auto_scan")
@login_required
def api_auto_scan():
    """Accepts one group photo, matches every detected face, and logs attendance once per student."""
    f = request.files.get("image")
    if not f:
        return jsonify({"ok": False, "error": "No image"}), 400

    img = bytes_to_ndarray(f.read())
    if img is None:
        return jsonify({"ok": False, "error": "Invalid image"}), 400

    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb, model="hog")
    if not boxes:
        return jsonify({"ok": True, "matches": [], "note": "no_faces"})

    encs = face_recognition.face_encodings(rgb, boxes)
    students = get_students()
    known = [s["encoding"] for s in students]
    settings = load_settings()
    tolerance = float(settings.get("tolerance", 0.45))

    unique_marked = set()
    matches = []
    for e in encs:
        idx, dist = match_encoding(e, known, tolerance=tolerance)
        if idx != -1:
            sid = students[idx]["id"]
            if sid in unique_marked:
                continue
            log_attendance(
                sid,
                subject=request.form.get("subject"),
                class_section=request.form.get("class_section"),
                device_id=request.form.get("device_id"),
            )
            unique_marked.add(sid)
            matches.append({"student_id": sid, "name": students[idx]["name"], "roll": students[idx]["roll"], "distance": dist})
    return jsonify({"ok": True, "matches": matches})


@app.get("/api/students")
@login_required
def api_students():
    return jsonify({"ok": True, "students": [
        {"id": s["id"], "name": s["name"], "roll": s["roll"], "class_section": s["class_section"]}
        for s in get_students()
    ]})


@app.get("/api/attendance")
@login_required
def api_attendance():
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    class_section = request.args.get("class_section")
    subject = request.args.get("subject")
    rows = get_attendance(date_from=date_from, date_to=date_to, class_section=class_section, subject=subject)
    data = [
        {"id": r[0], "name": r[1], "roll": r[2], "class_section": r[3], "timestamp": r[4], "subject": r[5]}
        for r in rows
    ]
    return jsonify({"ok": True, "data": data})


@app.get("/api/dashboard_stats")
@login_required
def api_dashboard_stats():
    class_section = request.args.get("class_section") or None
    subject = request.args.get("subject") or None
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None

    settings = load_settings()
    threshold = float(settings.get("attendance_alert_threshold", 75))

    stats = get_attendance_stats(class_section=class_section, subject=subject,
                                  date_from=date_from, date_to=date_to)
    defaulters = [s for s in stats if s["percentage"] is not None and s["percentage"] < threshold]
    total_sessions = get_session_count(class_section=class_section, subject=subject,
                                        date_from=date_from, date_to=date_to)

    return jsonify({
        "ok": True,
        "threshold": threshold,
        "total_sessions": total_sessions,
        "stats": stats,
        "defaulters": defaulters,
        "class_sections": get_distinct_class_sections(),
        "subjects": get_distinct_subjects(class_section=class_section),
    })


@app.post("/api/send_alerts")
@login_required
def api_send_alerts():
    if current_user.role != "admin":
        return jsonify({"ok": False, "error": "Admin only"}), 403

    class_section = request.form.get("class_section") or None
    subject = request.form.get("subject") or None
    date_from = request.form.get("date_from") or None
    date_to = request.form.get("date_to") or None

    settings = load_settings()
    threshold = float(settings.get("attendance_alert_threshold", 75))
    stats = get_attendance_stats(class_section=class_section, subject=subject,
                                  date_from=date_from, date_to=date_to)
    defaulters = [s for s in stats if s["percentage"] is not None and s["percentage"] < threshold]

    if not defaulters:
        return jsonify({"ok": True, "results": [], "note": "No students below threshold"})

    results = alerts.notify_defaulters(settings, defaulters)
    return jsonify({"ok": True, "results": results})


@app.get("/api/export_csv")
@login_required
def api_export_csv():
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    class_section = request.args.get("class_section")
    subject = request.args.get("subject")
    rows = get_attendance(date_from=date_from, date_to=date_to, class_section=class_section, subject=subject)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Name", "Roll", "Class", "Timestamp", "Subject"])
    for r in rows:
        writer.writerow([r[0], r[1], r[2], r[3], r[4], r[5] or ""])

    mem = io.BytesIO(output.getvalue().encode("utf-8-sig"))
    filename = f"attendance_{datetime.datetime.utcnow().date()}.csv"
    return send_file(mem, mimetype="text/csv", as_attachment=True, download_name=filename)


# ---------------------------------------------------------------------------
# Kiosk mode — intentionally PUBLIC (no login) so students can self-mark
# attendance by walking up to a mounted device. Only exposes recognition;
# no access to enroll/reports/settings/student list. Deploy this on a device
# placed in a supervised area (e.g. classroom entrance) since the liveness
# check is a best-effort deterrent, not a certified anti-spoofing system.
# ---------------------------------------------------------------------------
@app.route("/kiosk")
def kiosk_page():
    return render_template("kiosk.html", hide_nav=True)


@app.post("/api/kiosk_recognize")
def api_kiosk_recognize():
    subject = request.form.get("subject")
    class_section = request.form.get("class_section")
    f = request.files.get("image")
    f2 = request.files.get("image2")
    if not f:
        return jsonify({"ok": False, "error": "No image"}), 400

    img = bytes_to_ndarray(f.read())
    if img is None:
        return jsonify({"ok": False, "error": "Invalid image"}), 400
    img2 = bytes_to_ndarray(f2.read()) if f2 else None

    boxes, encs = compute_boxes_and_encodings_from_bgr(img)
    if not encs:
        return jsonify({"ok": True, "results": [], "note": "no_face_detected"})

    students = get_students()
    known = [s["encoding"] for s in students]
    settings = load_settings()
    tolerance = float(settings.get("tolerance", 0.45))
    liveness_enabled = bool(settings.get("liveness_enabled", True))

    results = []
    for box, e in zip(boxes, encs):
        live = check_liveness(img, img2, box) if (liveness_enabled and img2 is not None) else None
        if live is False:
            results.append({"match": False, "reason": "liveness_failed"})
            continue
        idx, dist = match_encoding(e, known, tolerance=tolerance)
        if idx != -1:
            sid = students[idx]["id"]
            log_attendance(sid, subject=subject, class_section=class_section, device_id="kiosk")
            results.append({"match": True, "name": students[idx]["name"], "roll": students[idx]["roll"]})
        else:
            results.append({"match": False})
    return jsonify({"ok": True, "results": results})


@app.errorhandler(401)
def unauthorized(e):
    return redirect(url_for("login_page"))


if __name__ == "__main__":
    app.run(debug=True)
