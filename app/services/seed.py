import json
from pathlib import Path
import psycopg
from app.db.repository import recompute_all_matches

SCHEMA_FILE = Path(__file__).parent.parent / "db" / "schema.sql"

def init_db(conn: psycopg.Connection) -> None:
    """Read and execute schema.sql DDL."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()

def recompute_matches(conn: psycopg.Connection) -> int:
    """Recomputes all candidate-job match scores via repository."""
    return recompute_all_matches(conn)

def seed_data(conn: psycopg.Connection, data_path: str = "docs/seed-data.json") -> dict:
    """Idempotently seeds database with candidates, jobs, skills, traits, and culture keywords."""
    path = Path(data_path)
    if not path.is_absolute():
        path = Path(__file__).parent.parent.parent / data_path

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    init_db(conn)

    candidates_count = 0
    jobs_count = 0

    with conn.transaction():
        with conn.cursor() as cur:
            # Seed candidates
            for cand in data.get("candidates", []):
                name = cand["name"].strip()
                exp = float(cand["experience_years"])
                avail = cand["availability"].strip()
                quirk = cand.get("quirk", "").strip()

                cur.execute(
                    """
                    INSERT INTO candidates (name, experience_years, availability, quirk)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (name) DO UPDATE SET
                        experience_years = EXCLUDED.experience_years,
                        availability = EXCLUDED.availability,
                        quirk = EXCLUDED.quirk
                    RETURNING id;
                    """,
                    (name, exp, avail, quirk)
                )
                cand_id = cur.fetchone()[0]
                candidates_count += 1

                # Delete existing candidate_skills & candidate_traits for this entity before re-inserting
                cur.execute("DELETE FROM candidate_skills WHERE candidate_id = %s;", (cand_id,))
                cur.execute("DELETE FROM candidate_traits WHERE candidate_id = %s;", (cand_id,))

                # Lowercase and strip skills/traits at ingestion
                for skill in cand.get("skills", []):
                    clean_skill = skill.strip().lower()
                    if not clean_skill:
                        continue
                    cur.execute(
                        """
                        INSERT INTO skills (name) VALUES (%s)
                        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                        RETURNING id;
                        """,
                        (clean_skill,)
                    )
                    skill_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO candidate_skills (candidate_id, skill_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (cand_id, skill_id)
                    )

                for trait in cand.get("traits", []):
                    clean_trait = trait.strip().lower()
                    if not clean_trait:
                        continue
                    cur.execute(
                        """
                        INSERT INTO candidate_traits (candidate_id, trait)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (cand_id, clean_trait)
                    )

            # Seed jobs
            for job in data.get("jobs", []):
                title = job["title"].strip()
                min_exp = float(job["min_experience"])
                tagline = job.get("tagline", "").strip()

                cur.execute(
                    """
                    INSERT INTO jobs (title, min_experience, tagline)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (title) DO UPDATE SET
                        min_experience = EXCLUDED.min_experience,
                        tagline = EXCLUDED.tagline
                    RETURNING id;
                    """,
                    (title, min_exp, tagline)
                )
                job_id = cur.fetchone()[0]
                jobs_count += 1

                # Delete existing job_skills & job_culture_keywords for this entity before re-inserting
                cur.execute("DELETE FROM job_skills WHERE job_id = %s;", (job_id,))
                cur.execute("DELETE FROM job_culture_keywords WHERE job_id = %s;", (job_id,))

                # Lowercase and strip required_skills/keywords at ingestion
                for skill in job.get("required_skills", []):
                    clean_skill = skill.strip().lower()
                    if not clean_skill:
                        continue
                    cur.execute(
                        """
                        INSERT INTO skills (name) VALUES (%s)
                        ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                        RETURNING id;
                        """,
                        (clean_skill,)
                    )
                    skill_id = cur.fetchone()[0]
                    cur.execute(
                        """
                        INSERT INTO job_skills (job_id, skill_id)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (job_id, skill_id)
                    )

                for kw in job.get("culture_keywords", []):
                    clean_kw = kw.strip().lower()
                    if not clean_kw:
                        continue
                    cur.execute(
                        """
                        INSERT INTO job_culture_keywords (job_id, keyword)
                        VALUES (%s, %s)
                        ON CONFLICT DO NOTHING;
                        """,
                        (job_id, clean_kw)
                    )

    # Recompute matches automatically after seeding
    matches_count = recompute_matches(conn)

    return {
        "status": "success",
        "candidates_seeded": candidates_count,
        "jobs_seeded": jobs_count,
        "matches_computed": matches_count
    }
