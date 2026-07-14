import sqlite3
from contextlib import contextmanager
from pathlib import Path
import json
import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "database.sqlite"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            roll TEXT NOT NULL UNIQUE,
            class_section TEXT NOT NULL,
            encoding_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS attendance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER NOT NULL,
            timestamp TEXT NOT NULL,
            date TEXT NOT NULL,
            subject TEXT,
            class_section TEXT,
            device_id TEXT,
            FOREIGN KEY(student_id) REFERENCES students(id)
        )
        """)
        conn.commit()

        # --- Migration-safe column additions for existing DBs ---
        c.execute("PRAGMA table_info(students)")
        cols = {row[1] for row in c.fetchall()}
        if "email" not in cols:
            c.execute("ALTER TABLE students ADD COLUMN email TEXT")
            conn.commit()


_init_db()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def add_student(name, roll, class_section, encoding_vec, email=None):
    enc_json = json.dumps(list(map(float, encoding_vec)))
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO students (name, roll, class_section, encoding_json, created_at, email)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, roll, class_section, enc_json, datetime.datetime.utcnow().isoformat(), email))
        conn.commit()
        return c.lastrowid


def get_students():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, roll, class_section, encoding_json, email FROM students ORDER BY id DESC")
        rows = c.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r[0], "name": r[1], "roll": r[2], "class_section": r[3],
                "encoding": json.loads(r[4]), "email": r[5]
            })
        return result


def get_student_by_roll(roll):
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT id, name, roll, class_section, email FROM students WHERE roll = ?", (roll,))
        r = c.fetchone()
        if not r:
            return None
        return {"id": r[0], "name": r[1], "roll": r[2], "class_section": r[3], "email": r[4]}


def log_attendance(student_id, subject=None, class_section=None, device_id=None, timestamp=None):
    ts = timestamp or datetime.datetime.utcnow().isoformat()
    date = ts.split("T")[0]
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("""
            INSERT INTO attendance (student_id, timestamp, date, subject, class_section, device_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (student_id, ts, date, subject, class_section, device_id))
        conn.commit()
        return c.lastrowid


def get_attendance(date_from=None, date_to=None, class_section=None, subject=None):
    q = ("SELECT attendance.id, students.name, students.roll, students.class_section, "
         "attendance.timestamp, attendance.subject FROM attendance "
         "JOIN students ON attendance.student_id = students.id")
    conds = []
    params = []
    if date_from:
        conds.append("attendance.date >= ?")
        params.append(date_from)
    if date_to:
        conds.append("attendance.date <= ?")
        params.append(date_to)
    if class_section:
        conds.append("students.class_section = ?")
        params.append(class_section)
    if subject:
        conds.append("attendance.subject = ?")
        params.append(subject)
    if conds:
        q += " WHERE " + " AND ".join(conds)
    q += " ORDER BY attendance.timestamp DESC"
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(q, params)
        rows = c.fetchall()
        return rows


# ---------------------------------------------------------------------------
# Dashboard / attendance-percentage helpers
# ---------------------------------------------------------------------------
def get_distinct_class_sections():
    with get_conn() as conn:
        c = conn.cursor()
        c.execute("SELECT DISTINCT class_section FROM students ORDER BY class_section")
        return [r[0] for r in c.fetchall()]


def get_distinct_subjects(class_section=None):
    q = "SELECT DISTINCT subject FROM attendance WHERE subject IS NOT NULL AND subject != ''"
    params = []
    if class_section:
        q += " AND class_section = ?"
        params.append(class_section)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(q, params)
        return [r[0] for r in c.fetchall()]


def get_session_count(class_section=None, subject=None, date_from=None, date_to=None):
    """A 'session' = one distinct date on which attendance was taken for this class/subject."""
    q = "SELECT COUNT(DISTINCT date) FROM attendance WHERE 1=1"
    params = []
    if class_section:
        q += " AND class_section = ?"
        params.append(class_section)
    if subject:
        q += " AND subject = ?"
        params.append(subject)
    if date_from:
        q += " AND date >= ?"
        params.append(date_from)
    if date_to:
        q += " AND date <= ?"
        params.append(date_to)
    with get_conn() as conn:
        c = conn.cursor()
        c.execute(q, params)
        return c.fetchone()[0] or 0


def get_attendance_stats(class_section=None, subject=None, date_from=None, date_to=None):
    """
    Returns a list of dicts per student in `class_section` (or all students if None):
    {id, name, roll, class_section, email, present_days, total_sessions, percentage}
    """
    total_sessions = get_session_count(class_section=class_section, subject=subject,
                                        date_from=date_from, date_to=date_to)

    student_q = "SELECT id, name, roll, class_section, email FROM students"
    student_params = []
    if class_section:
        student_q += " WHERE class_section = ?"
        student_params.append(class_section)
    student_q += " ORDER BY name"

    with get_conn() as conn:
        c = conn.cursor()
        c.execute(student_q, student_params)
        students = c.fetchall()

        stats = []
        for s in students:
            sid = s[0]
            q = "SELECT COUNT(DISTINCT date) FROM attendance WHERE student_id = ?"
            params = [sid]
            if subject:
                q += " AND subject = ?"
                params.append(subject)
            if date_from:
                q += " AND date >= ?"
                params.append(date_from)
            if date_to:
                q += " AND date <= ?"
                params.append(date_to)
            c.execute(q, params)
            present_days = c.fetchone()[0] or 0
            pct = round((present_days / total_sessions) * 100, 1) if total_sessions > 0 else None
            stats.append({
                "id": sid, "name": s[1], "roll": s[2], "class_section": s[3], "email": s[4],
                "present_days": present_days, "total_sessions": total_sessions, "percentage": pct,
            })
        return stats
