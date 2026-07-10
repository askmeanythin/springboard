from faker import Faker
import csv
import random

fake = Faker()

subjects = [
    "Python",
    "Java",
    "DBMS",
    "Operating Systems",
    "Computer Networks",
    "Artificial Intelligence"
]

with open("sample_candidates.csv", "w", newline="") as file:

    writer = csv.writer(file)

    writer.writerow([
        "Candidate ID",
        "Name",
        "Email",
        "Age",
        "Exam Subject"
    ])

    for i in range(1, 21):

        candidate_id = f"C{i:03}"

        name = fake.name()

        email = fake.email()

        age = random.randint(18, 30)

        subject = random.choice(subjects)

        writer.writerow([
            candidate_id,
            name,
            email,
            age,
            subject
        ])

print("20 Sample Candidate Records Generated Successfully!")