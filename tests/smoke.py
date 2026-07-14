from app import db
print("DB path:", db.DB_PATH)
students = db.get_students()
print("Students loaded:", len(students))
