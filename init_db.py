import sqlite3

# Connect (will create file if it doesn't exist)
conn = sqlite3.connect("students.db")
cur = conn.cursor()

# Drop table if it already exists (for re-run)
cur.execute("DROP TABLE IF EXISTS students")

# Create students table
cur.execute("""
CREATE TABLE students (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    dept TEXT NOT NULL,
    year INTEGER NOT NULL,
    city TEXT NOT NULL,
    cgpa REAL NOT NULL
)
""")

# Sample data
students_data = [
    ("Arun Kumar",  "CSE", 3, "Chennai",    8.4),
    ("Sanjay",      "CSE", 2, "Coimbatore", 9.1),
    ("Priya",       "ECE", 4, "Chennai",    7.8),
    ("Divya",       "EEE", 1, "Madurai",    8.0),
    ("Rahul",       "MECH",3, "Chennai",    6.9),
    ("Anitha",      "CSE", 1, "Salem",      9.3),
    ("Vignesh",     "ECE", 2, "Coimbatore", 7.5),
    ("Karthik",     "CSE", 4, "Chennai",    8.9),
    ("Meena",       "IT",  3, "Trichy",     8.2),
    ("Harini",      "IT",  2, "Chennai",    9.0),
]

cur.executemany(
    "INSERT INTO students (name, dept, year, city, cgpa) VALUES (?, ?, ?, ?, ?)",
    students_data
)

conn.commit()
conn.close()

print("✅ Database 'students.db' created with sample data.")
