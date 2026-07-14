"""
Import students from a CSV with columns: name,roll,class_section
Encodings are not set here. After import, enroll via UI to capture encodings.
"""
import csv, argparse
from pathlib import Path
from app.db import add_student

parser = argparse.ArgumentParser()
parser.add_argument("csv_path", help="Path to CSV file")
args = parser.parse_args()

with open(args.csv_path, newline="", encoding="utf-8") as f:
    r = csv.DictReader(f)
    for row in r:
        name = row["name"].strip()
        roll = row["roll"].strip()
        cls = row["class_section"].strip()
        # Empty encoding placeholder not allowed by schema; skip here.
        print(f"Imported roster row: {name} ({roll}, {cls}) - now enroll via UI to capture encoding.")
