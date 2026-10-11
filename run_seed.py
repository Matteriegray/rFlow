import sys
import psycopg
from psycopg.rows import dict_row
from app.config import settings
from app.services.seed import seed_data

def main():
    print(f"Connecting to database at {settings.database_url}...")
    try:
        conn = psycopg.connect(settings.database_url)
    except Exception as e:
        print(f"Error connecting to database: {e}")
        print("\nPlease update your DATABASE_URL in .env with your PostgreSQL credentials.")
        sys.exit(1)

    print("Running seed service...")
    result = seed_data(conn)
    print(f"Seeding completed: {result}\n")

    print("--- Database Table Row Counts ---")
    tables = [
        "candidates",
        "jobs",
        "skills",
        "candidate_skills",
        "job_skills",
        "candidate_traits",
        "job_culture_keywords",
        "matches"
    ]

    with conn.cursor(row_factory=dict_row) as cur:
        for table in tables:
            cur.execute(f"SELECT COUNT(*) AS count FROM {table};")
            count = cur.fetchone()["count"]
            print(f"{table:25s}: {count} rows")

    conn.close()

if __name__ == "__main__":
    main()
