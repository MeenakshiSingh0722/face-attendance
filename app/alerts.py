"""
Sends low-attendance email alerts using SMTP settings stored in data/settings.json
(editable via the Settings page in the UI).

SMS is not wired to a live provider (no API keys can be created here), but is left
as a documented hook below — swap in Twilio/Fast2SMS/etc. in `send_sms` and call
it from `notify_defaulters` alongside email.
"""
import smtplib
import ssl
from email.mime.text import MIMEText


def send_email(settings, to_addr, subject, body):
    host = settings.get("smtp_host")
    port = int(settings.get("smtp_port", 587))
    username = settings.get("smtp_username")
    password = settings.get("smtp_password")
    from_addr = settings.get("smtp_from") or username
    use_tls = settings.get("smtp_use_tls", True)

    if not host or not username or not to_addr:
        return False, "SMTP is not configured (set Host/Username/From in Settings) or recipient has no email."

    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr

    try:
        if use_tls:
            context = ssl.create_default_context()
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=context)
                server.login(username, password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP_SSL(host, port, timeout=15) as server:
                server.login(username, password)
                server.sendmail(from_addr, [to_addr], msg.as_string())
        return True, "sent"
    except Exception as e:
        return False, str(e)


def send_sms(settings, phone_number, body):
    """
    Placeholder hook for SMS. To enable real SMS delivery:
      1. Sign up for an SMS API provider (Twilio, MSG91, Fast2SMS, etc.)
      2. pip install twilio  (or the relevant provider SDK)
      3. Store the provider's API key/SID in settings.json (add fields via Settings page)
      4. Replace the body of this function with the provider's send call.
    Returns (False, "not_configured") until wired to a real provider.
    """
    return False, "SMS provider not configured"


def notify_defaulters(settings, defaulters):
    """
    defaulters: list of student stat dicts (from db.get_attendance_stats) that are
    below the configured threshold. Sends one email per student who has an email
    on file. Returns a list of {student, ok, detail} result dicts.
    """
    threshold = settings.get("attendance_alert_threshold", 75)
    results = []
    for s in defaulters:
        if not s.get("email"):
            results.append({"student": s["name"], "ok": False, "detail": "No email on file"})
            continue
        subject = f"Attendance Alert: {s['name']} ({s['roll']}) below {threshold}%"
        body = (
            f"Dear {s['name']},\n\n"
            f"Your attendance in {s['class_section']} is currently {s['percentage']}% "
            f"({s['present_days']} of {s['total_sessions']} sessions attended), "
            f"which is below the required {threshold}%.\n\n"
            f"Please contact your class coordinator if you believe this is in error.\n\n"
            f"- Automated Attendance System"
        )
        ok, detail = send_email(settings, s["email"], subject, body)
        results.append({"student": s["name"], "ok": ok, "detail": detail})
    return results
