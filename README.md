# Face Recognition Attendance System

A Flask-based attendance system that enrolls students via webcam face samples and
marks attendance by recognizing faces live, from a group photo, or via a self-service kiosk.

---

## 🔧 What was fixed from the original code

The original project had 3 bugs that prevented it from running at all, plus an unprotected,
unstyled login flow:

| # | Bug | Fix |
|---|-----|-----|
| 1 | `/login` route defined **twice** → Flask crashes on startup (`AssertionError: View function mapping is overwriting an existing endpoint`). | Merged into one `/login` route. |
| 2 | `db_extra.py` used a relative import (`from .db import ...`) but was loaded as a flat module → `ImportError`. | Changed to `from db import DB_PATH, get_conn`. |
| 3 | `/api/auto_scan` used `cv2`/`face_recognition` without importing them → `NameError` at request time. | Added the missing imports. |
| 4 | Login page was a bare unstyled `<form>` — no error display, no password toggle, no loading state. | Rebuilt as a centered card with logo, inline error alert, show/hide password, disabled+spinner state on submit. |
| 5 | Every page and API route was reachable **without logging in** — only the nav link hid itself. | Added `@login_required` everywhere; `/settings` and `/bulk_import` also require `role == 'admin'`. |
| 6 | Flask `secret_key` silently fell back to a hardcoded string if `data/secret.key` was missing. | Now auto-generates and persists a random 64-char key on first run. |

The whole UI was also restyled with a consistent design system (`app/static/css/styles.css`).

---

## ✨ Features added beyond the original scope

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
   Exposes nothing except recognition.
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
│                            # (gitignored — auto-created on first run, see data/.gitkeep)
├── scripts/                 # CLI bulk-import / CSV import helpers
├── tests/smoke.py           # tiny sanity script
├── requirements.txt
├── wsgi.py                  # production entrypoint (gunicorn/waitress)
├── Procfile                 # for Heroku/Render
└── Dockerfile
```

---

## 📤 Pushing this to GitHub

This project already has a local git repo initialized with one commit, and a `.gitignore` that
correctly excludes generated secrets/data (`data/database.sqlite`, `data/secret.key`,
`data/settings.json`, `venv/`, `__pycache__/`).

1. Create a new **empty** repository on GitHub (don't add a README/license there — this project
   already has its own, and that would conflict on push).
2. From inside the project folder:
   ```bash
   git remote add origin https://github.com/<your-username>/<your-repo-name>.git
   git branch -M main
   git push -u origin main
   ```
   If you extracted this as a plain ZIP (no `.git` folder included), run this first:
   ```bash
   git init
   git add -A
   git commit -m "Initial commit"
   ```
   then the three commands above.
3. Sanity-check nothing sensitive got committed:
   ```bash
   git ls-files | grep -E "secret.key|database.sqlite|settings.json"
   ```
   This should print **nothing**. If something shows up, remove it with `git rm --cached <file>`
   and commit again before pushing.

---

## 🚀 Running it locally, end to end

### 1. Prerequisites
- Python 3.10 (dlib/face_recognition wheels are most reliable on this version)
- Windows: Visual Studio Build Tools (C++) if `dlib` needs to compile
- Linux: `sudo apt-get install build-essential cmake libopenblas-dev liblapack-dev`
- A webcam

### 2. Set up
```bash
git clone https://github.com/<your-username>/<your-repo-name>.git
cd <your-repo-name>

python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac

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

## ☁️ Deploying this web application

Face recognition (`dlib`/`face_recognition`) is CPU/memory-heavy with native system libraries, so
**serverless platforms (plain Vercel/Netlify functions) will not work well** — use a platform that
gives you a real Linux VM/container.

### Option A — Docker (any VPS: DigitalOcean, AWS EC2, GCP, Azure, Render, Railway, Fly.io)
```bash
docker build -t face-attendance .
docker run -d -p 8000:8000 \
  -v $(pwd)/data:/srv/app/data \
  --name face-attendance \
  face-attendance
```
Mounting `data/` keeps your SQLite DB, secret key, and settings across container restarts.
Visit `http://<your-server-ip>:8000`, and put Nginx/Caddy with HTTPS in front for real use —
browsers block camera access (`getUserMedia`) on plain HTTP for any non-localhost origin.

### Option B — Traditional VPS (no Docker)
1. SSH in, install Python 3.10 + build tools (see Prerequisites above).
2. `git clone` the repo, create a venv, `pip install -r requirements.txt`.
3. Run with a production WSGI server, not the Flask dev server:
   ```bash
   gunicorn -w 2 -k gthread -b 0.0.0.0:8000 wsgi:app
   ```
4. Put Nginx in front as a reverse proxy with a Let's Encrypt cert (`certbot`), forwarding
   `443` → `127.0.0.1:8000`.
5. Use `systemd` (or `supervisor`) to keep gunicorn running and auto-restart on crash.

### Option C — Heroku / Render (Procfile-based)
1. Push this repo to GitHub (see steps above).
2. Create a new Web Service on Render (or a Heroku app) pointing at the repo.
3. It auto-detects `requirements.txt` and the included `Procfile`
   (`web: gunicorn -w 2 -k gthread -b 0.0.0.0:$PORT wsgi:app`) — no extra config needed.
4. **Attach a persistent disk** (e.g. Render "Disk") mounted so `data/` survives redeploys —
   most PaaS containers have ephemeral filesystems, which would otherwise wipe your enrolled
   students and attendance history on every deploy.

### Pre-launch checklist
- [ ] Change the default `admin/admin` password immediately after first login.
- [ ] Serve over **HTTPS** — required for camera access on any non-localhost domain.
- [ ] Confirm you're running via `wsgi.py` + gunicorn/waitress, not `python app.py` (dev server).
- [ ] Persist the `data/` folder outside the container/instance so redeploys don't erase data.
- [ ] Back up `data/database.sqlite` regularly (or migrate to Postgres for larger deployments).
- [ ] Treat `data/secret.key` as a credential — never commit it (already gitignored here).

---

## 🧪 Sanity check
```bash
python tests/smoke.py
```
Confirms the DB path resolves and prints how many students are currently enrolled.
