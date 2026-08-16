import sqlite3
import os
import shutil

DB_PATH = "database/exam.db"
SCREENSHOT_FOLDER = "screenshots"

conn = sqlite3.connect(DB_PATH)

conn.execute("PRAGMA foreign_keys = ON")

cursor = conn.cursor()


print("\n========== BEFORE EVIDENCE RESET ==========")


# ---------------------------------------------------------
# DATABASE EVIDENCE
# ---------------------------------------------------------

cursor.execute("""
    SELECT COUNT(*)
    FROM Screenshot
""")

screenshot_count = cursor.fetchone()[0]

print("Screenshot database records:", screenshot_count)


# ---------------------------------------------------------
# SHOW CURRENT DATABASE PATHS
# ---------------------------------------------------------

cursor.execute("""
    SELECT
        screenshot_id,
        session_id,
        screenshot_path,
        image_type
    FROM Screenshot
    ORDER BY screenshot_id
""")

rows = cursor.fetchall()


for row in rows:

    print(
        "ID:", row[0],
        "| Session:", row[1],
        "| Path:", row[2],
        "| Type:", row[3]
    )


# ---------------------------------------------------------
# DELETE OLD DATABASE EVIDENCE
# ---------------------------------------------------------

cursor.execute("""
    DELETE FROM Screenshot
""")


deleted_database_records = cursor.rowcount


# ---------------------------------------------------------
# DELETE PHYSICAL SCREENSHOTS
# ---------------------------------------------------------

deleted_files = 0


if os.path.exists(SCREENSHOT_FOLDER):

    for item in os.listdir(SCREENSHOT_FOLDER):

        item_path = os.path.join(
            SCREENSHOT_FOLDER,
            item
        )

        if os.path.isdir(item_path):

            shutil.rmtree(item_path)

            deleted_files += 1

        else:

            os.remove(item_path)

            deleted_files += 1


# ---------------------------------------------------------
# COMMIT
# ---------------------------------------------------------

conn.commit()


print("\n========== AFTER EVIDENCE RESET ==========")


cursor.execute("""
    SELECT COUNT(*)
    FROM Screenshot
""")

remaining_records = cursor.fetchone()[0]


print(
    "Deleted database evidence:",
    deleted_database_records
)

print(
    "Remaining database evidence:",
    remaining_records
)

print(
    "Deleted screenshot folders/files:",
    deleted_files
)


conn.close()


print("\nEvidence reset complete.")
print("The screenshots folder is now ready for new evidence.")