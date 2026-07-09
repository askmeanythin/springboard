import sqlite3

conn = sqlite3.connect("database/exam.db")
cursor = conn.cursor()

cursor.execute()

cursor.execute()

conn.commit()
conn.close()

print("Database and tables created successfully!")