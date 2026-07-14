"""
Bulk-enroll students from a ZIP of photos uploaded via the web UI.

Expected image filenames inside the ZIP: <roll>_anything.jpg or <roll>.jpg
e.g. 2021CS101_1.jpg, 2021CS101_2.jpg, 2021CS102.jpg

An optional mapping CSV (columns: roll,name,class_section) supplies the
student's name/class; if omitted, name defaults to the roll number and
class_section defaults to "Unknown" (editable later isn't supported yet —
better to include the mapping CSV for real rosters).
"""
import csv
import io
import re
import zipfile

import cv2
import numpy as np
import face_recognition

from db import add_student

ROLL_PATTERN = re.compile(r"^([^_.]+)")
VALID_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def _parse_mapping_csv(csv_bytes):
    mapping = {}
    text = csv_bytes.decode("utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        roll = (row.get("roll") or "").strip()
        if not roll:
            continue
        name = (row.get("name") or "").strip() or roll
        cls = (row.get("class_section") or "").strip() or "Unknown"
        mapping[roll] = (name, cls)
    return mapping


def process_zip(zip_bytes, mapping_csv_bytes=None):
    """
    Returns a list of result dicts:
      {"roll": ..., "name": ..., "status": "added"|"skipped"|"error", "detail": ..., "student_id": ...}
    """
    mapping = _parse_mapping_csv(mapping_csv_bytes) if mapping_csv_bytes else {}
    results = []

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile:
        return [{"roll": None, "name": None, "status": "error", "detail": "Uploaded file is not a valid ZIP"}]

    groups = {}
    for name in zf.namelist():
        if name.endswith("/") or name.startswith("__MACOSX"):
            continue
        lower = name.lower()
        if not any(lower.endswith(ext) for ext in VALID_EXTS):
            continue
        base = name.rsplit("/", 1)[-1]
        m = ROLL_PATTERN.match(base)
        if not m:
            continue
        roll = m.group(1)
        groups.setdefault(roll, []).append(name)

    if not groups:
        return [{"roll": None, "name": None, "status": "error",
                  "detail": "No recognizable image files found in the ZIP (expected <roll>_x.jpg)"}]

    for roll, filenames in groups.items():
        encs = []
        for fn in filenames:
            try:
                data = zf.read(fn)
                arr = np.frombuffer(data, dtype=np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                boxes = face_recognition.face_locations(rgb, model="hog")
                if not boxes:
                    continue
                e = face_recognition.face_encodings(rgb, boxes)
                encs.extend(e)
            except Exception:
                continue

        name, cls = mapping.get(roll, (roll, "Unknown"))

        if not encs:
            results.append({"roll": roll, "name": name, "status": "error",
                             "detail": "No face detected in any provided image(s)"})
            continue

        avg = np.array(encs).mean(axis=0)
        try:
            sid = add_student(name, roll, cls, avg.tolist())
            results.append({"roll": roll, "name": name, "status": "added",
                             "detail": f"{len(filenames)} image(s) processed", "student_id": sid})
        except Exception as e:
            results.append({"roll": roll, "name": name, "status": "error",
                             "detail": f"Could not save (duplicate roll?): {e}"})

    return results
