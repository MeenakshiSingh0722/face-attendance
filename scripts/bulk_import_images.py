"""
Bulk import images folder and create student encodings automatically.
Image files must be named as <roll>_<anything>.jpg or <roll>.jpg
Example: 2021CS101_pic1.jpg  or  2021CS101.jpg
For each unique roll, this script computes encodings from all images matching that roll, averages them,
and creates a new student entry (name is roll unless provided via CSV mapping).
"""
import argparse, os, re, json
from pathlib import Path
import cv2, numpy as np
import face_recognition
from app.db import add_student, get_students

parser = argparse.ArgumentParser()
parser.add_argument("images_folder", help="Folder containing images")
parser.add_argument("--mapping", help="Optional CSV mapping roll->name,class_section", default=None)
args = parser.parse_args()

mapping = {}
if args.mapping:
    import csv
    with open(args.mapping, newline='', encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            mapping[row['roll'].strip()] = (row.get('name','').strip() or row['roll'].strip(), row.get('class_section','').strip() or 'Unknown')

folder = Path(args.images_folder)
if not folder.exists():
    print("Folder not found:", folder); exit(1)

pattern = re.compile(r'^([^_\.]+)')
groups = {}
for p in folder.iterdir():
    if not p.is_file(): continue
    m = pattern.match(p.name)
    if not m: continue
    roll = m.group(1)
    groups.setdefault(roll, []).append(str(p))

for roll, files in groups.items():
    encs = []
    for fp in files:
        img = cv2.imread(fp)
        if img is None: continue
        rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        boxes = face_recognition.face_locations(rgb, model='hog')
        if not boxes: continue
        e = face_recognition.face_encodings(rgb, boxes)
        if e:
            encs.extend(e)
    if not encs:
        print("No face data for", roll); continue
    avg = np.array(encs).mean(axis=0)
    name, cls = mapping.get(roll, (roll, 'Unknown'))
    sid = add_student(name, roll, cls, avg.tolist())
    print("Added", name, roll, "-> id", sid)
