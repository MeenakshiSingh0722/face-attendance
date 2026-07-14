# Face Recognition Attendance System

A Flask-based attendance system that enrolls students via webcam face samples and
marks attendance by recognizing faces live, from a group photo, or via a self-service kiosk.

**Live deployment:** `https://face-attendance-system.up.railway.app/` (hosted on Railway)

---

## ✨ Features

1. **Dashboard** (`/dashboard`) — Chart.js bar chart of per-student attendance %, filterable by
   class/subject/date range, plus a defaulters table (students below a configurable threshold).
2. **Low-attendance email alerts** (Dashboard → "Send Alerts to Defaulters") — real SMTP email to
   any defaulter with an email on file. Configure your provider in `/settings`. SMS is **not**
   wired to a live provider — `app/alerts.py::send_sms` is a documented stub for your own
   Twilio/MSG91/etc. integration.
3. **Liveness / anti-spoofing check** (`app/face_engine.py::check_liveness`) — the Attendance and
   Kiosk pages capture two frames ~0.6–0.8s apart; the backend compares pixel motion in the face
   region and rejects matches that look like a static printed photo/screen. Toggle in `/settings`.
   This is a best-effort deterrent, not certified anti-spoofing.
4. **Self-service Kiosk mode** (`/kiosk`, no login) — mount a device at a classroom entrance;
   students look at the camera and are recognized + marked present automatically (liveness-checked).
5. **Bulk student import** (`/bulk_import`, admin only) — upload a ZIP of photos named
   `<roll>_anything.jpg` plus an optional roster CSV (`roll,name,class_section`); the server groups
   images by roll, computes encodings, and enrolls everyone in one pass.
6. **Account page** (`/account`) — change your own username (separate from Change Password).
7. Optional per-student **email** field (Enroll / Bulk Import), used only for alerts.

### Editing the subject list
`app/static/timetable.json` maps each class/section to its subject list, shown in the Attendance
and Kiosk dropdowns — edit it directly, no code change needed:
```json
{
  "CSE-A": ["DBMS", "OS", "TOC", "Computer Networks"],
  "CSE-B": ["AI", "ML", "DS", "Computer Networks"],
  "Common": ["Workshop", "Seminar", "Library"]
}
```

---

## 📁 Project Structure

```
Face-Recognition-Based-Attendance-System-main/
├── app/
│   ├── app.py              # Flask routes (pages + JSON API)
│   ├── db.py                # students & attendance tables, stats queries
│   ├── db_extra.py          # users table + app settings (tolerance, SMTP, threshold)
│   ├── face_engine.py       # detection/encoding/matching/liveness (face_recognition + cv2)
│   ├── alerts.py             # SMTP email alerts (+ documented SMS hook)
│   ├── bulk_import.py        # ZIP-based bulk enrollment
│   ├── static/
│   │   ├── css/styles.css
│   │   ├── js/webcam.js
│   │   └── timetable.json   # subject list per class
│   └── templates/           # Jinja2 templates
├── data/                    # runtime-generated: database.sqlite, secret.key, settings.json
│                            # (gitignored — auto-created on first run, persisted via Railway volume)
├── scripts/                 # CLI bulk-import / CSV import helpers
├── tests/smoke.py           # tiny sanity script
├── requirements.txt
├── wsgi.py                  # production entrypoint (gunicorn/waitress)
├── Procfile                 # for Heroku/Render
└── Dockerfile
```

---

## 🗄️ Database

SQLite, stored at `data/database.sqlite` inside the persistent Railway volume. Three tables:

| Table | Contents |
|---|---|
| `students` | Enrolled students — roll no, name, class/section, email, face encoding |
| `attendance` | Attendance records — student, subject, class, timestamp |
| `users` | Login accounts — username, password hash, role (`admin` / regular) |

### Inspecting the database (Railway Console)
The container doesn't include the `sqlite3` CLI, so use Python's built-in module instead.
In Railway → your service → **Console** tab:

```bash
python3
```

Then inside the Python shell:
```python
import sqlite3
conn = sqlite3.connect('data/database.sqlite')
cur = conn.cursor()

# List tables
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print(cur.fetchall())

# View students
cur.execute("SELECT * FROM students;")
print(cur.fetchall())

# View attendance
cur.execute("SELECT * FROM attendance;")
print(cur.fetchall())

# View a table's columns
cur.execute("PRAGMA table_info(students);")
print(cur.fetchall())
```
Type `exit()` when done.

---

## 🚀 Running it locally (Windows)

### 1. Prerequisites
- Python 3.10 (dlib/face_recognition wheels are most reliable on this version)
- Windows: Visual Studio Build Tools (C++) if `dlib` needs to compile
- A webcam

### 2. Set up
```bash
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>

python -m venv venv
venv\Scripts\activate        # Windows

pip install -r requirements.txt
```
> If `dlib`/`face-recognition` fails to build, `dlib_bin==19.24.6` (already in requirements.txt)
> installs a pre-built wheel instead of compiling from source.

### 3. Run
```bash
cd app
python app.py
```
Visit **http://127.0.0.1:5000** — you'll be redirected to `/login`.

### 4. Log in and secure the account
- Default: **admin / admin** (auto-created on first run).
- Go to **Change Password** immediately — this matters before deploying anywhere reachable by others.

### 5. Enroll students
**Enroll** → Name/Roll/Class(/Email) → Start Camera → capture 5-10 samples → Save.

**Tips for clean face captures** (avoids "No face detected in the captured samples"):
- Face a light source — don't have a bright window/light behind you.
- Hold the phone/camera steady, roughly arm's length away, facing you directly.
- Keep your full face in frame and well-lit (forehead to chin, both eyes visible).

Or use **Bulk Import** (admin) to enroll many students at once from a ZIP of photos.

### 6. Mark attendance
**Attendance** → choose Subject/Class → Start Camera → **Mark** (single face) or enable
**Auto-scan** (group photo, marks everyone recognized). Or point students at **`/kiosk`** for
self-service check-in with no login.

### 7. Reports & Dashboard
**Reports** → filter/export CSV. **Dashboard** → attendance % chart, defaulters, and
"Send Alerts to Defaulters" (needs SMTP configured in Settings).

### 8. Tune settings (admin)
**Settings** → face-match tolerance, liveness toggle, low-attendance threshold, SMTP config.

---

## ☁️ Deploying (Railway — what this project actually uses)

Face recognition (`dlib`/`face_recognition`) is CPU/memory-heavy with native system libraries, so
**serverless platforms (plain Vercel/Netlify functions) will not work** — Railway gives a real
container with a Dockerfile build, which is what this repo is set up for.

### Steps
1. Push the repo to GitHub.
2. On [railway.app](https://railway.app), **New Project → Deploy from GitHub repo** → select the repo.
   Railway auto-detects the `Dockerfile` and builds it.
3. **Settings → Volumes** → add a volume mounted at `/srv/app/data`. This is critical — without
   it, every redeploy wipes the SQLite DB, secret key, and settings (Railway containers have an
   ephemeral filesystem otherwise).
4. **Settings → Networking** → click **Generate Domain** for a free `https://<name>.up.railway.app`
   URL with HTTPS already on (required — browsers block webcam access over plain HTTP for any
   non-localhost origin). You can rename the subdomain here, or attach a custom domain instead.
5. Visit the generated URL, log in with `admin` / `admin`, and change the password immediately.

### ⚠️ Dockerfile gotcha we hit (already fixed in this repo)
The original `CMD` used JSON/exec array form:
```dockerfile
CMD ["gunicorn", "-w", "2", "-k", "gthread", "-b", "0.0.0.0:8000", "wsgi:app"]
```
This form does **not** expand shell environment variables, so Railway's injected `$PORT` wasn't
resolving and the container crash-looped with `Error: '$PORT' is not a valid port number.`
Fixed by switching to shell form so `${PORT:-8000}` actually expands:
```dockerfile
CMD gunicorn -w 2 -k gthread -b 0.0.0.0:${PORT:-8000} wsgi:app
```
If you fork/rebuild this project elsewhere and hit the same crash, also check
**Settings → Deploy → Custom Start Command** in Railway — a value set there overrides the
Dockerfile's `CMD` entirely and can reintroduce this exact bug.

### Other supported deployment paths
- **Any VPS + Docker** (DigitalOcean, EC2, GCP, Azure, Render, Fly.io): same `Dockerfile`, put
  Nginx/Caddy in front for HTTPS.
- **Traditional VPS, no Docker**: `gunicorn -w 2 -k gthread -b 0.0.0.0:8000 wsgi:app` behind Nginx
  + certbot, run under systemd.
- **Heroku/Render (Procfile-based)**: auto-detects `requirements.txt` and the included `Procfile`.

### Pre-launch checklist
- [x] Change the default `admin/admin` password immediately after first login.
- [x] Serve over **HTTPS** — required for camera access on any non-localhost domain.
- [x] Confirm you're running via `wsgi.py` + gunicorn, not `python app.py` (dev server).
- [x] Persist the `data/` folder via a mounted volume so redeploys don't erase data.
- [ ] Back up `data/database.sqlite` regularly (or migrate to Postgres for larger deployments).
- [x] Treat `data/secret.key` as a credential — never commit it (already gitignored).

---

## 🐛 Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Container crash loop, log shows `Error: '$PORT' is not a valid port number.` | Dockerfile `CMD` in exec/array form doesn't expand `$PORT` | Use shell form: `CMD gunicorn ... -b 0.0.0.0:${PORT:-8000} wsgi:app`. Also clear any Custom Start Command in Railway settings. |
| Browser shows `DNS_PROBE_FINISHED_NXDOMAIN` on the Railway URL | Domain not generated yet, DNS propagation delay, or local ISP/router DNS caching | Confirm domain exists under Settings → Networking; wait a minute and retry; try incognito; switch Windows DNS to `8.8.8.8` / `1.1.1.1` and run `ipconfig /flushdns`. |
| "No face detected in the captured samples" during Enroll | Backlighting, motion blur, or bad camera angle | Face a light source (don't back it), hold the camera steady at eye level, keep full face in frame and well-lit. |
| Students/attendance disappear after a redeploy | No persistent volume attached | Add a volume mounted at `/srv/app/data` in Railway Settings → Volumes. |

---

## 🧪 Sanity check
```bash
python tests/smoke.py
```
Confirms the DB path resolves and prints how many students are currently enrolled.
