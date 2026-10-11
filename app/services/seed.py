import json
from pathlib import Path
import psycopg
from psycopg.rows import dict_row

SCHEMA_FILE = Path(__file__).parent.parent / "db" / "schema.sql"

def init_db(conn: psycopg.Connection) -> None:
    """Read and execute schema.sql DDL."""
    with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
        schema_sql = f.read()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()

def recompute_matches(conn: psycopg.Connection) -> int:
    """Recomputes all candidate-job match scores using SQL correlated subqueries and Python weighting."""
    match_query = """
    SELECT * FROM (
        SELECT 
            c.id AS candidate_id,
            c.name AS candidate_name,
            c.experience_years AS candidate_exp,
            c.availability AS candidate_avail,
            j.id AS job_id,
            j.title AS job_title,
            j.min_experience AS job_min_exp,
            (
                SELECT COUNT(*) 
                FROM job_skills js 
                JOIN candidate_skills cs ON js.skill_id = cs.skill_id 
                WHERE js.job_id = j.id AND cs.candidate_id = c.id
            ) AS matched_skills,
            (
                SELECT COUNT(*) 
                FROM job_skills js 
                WHERE js.job_id = j.id
            ) AS total_skills,
            (
                SELECT COUNT(*) 
                FROM job_culture_keywords jck 
                JOIN candidate_traits ct ON jck.keyword = ct.trait 
                WHERE jck.job_id = j.id AND ct.candidate_id = c.id
            ) AS matched_culture,
            (
                SELECT COUNT(*) 
                FROM job_culture_keywords jck 
                WHERE jck.job_id = j.id
            ) AS total_culture,
            (
                SELECT COALESCE(string_agg(s.name, ', '), '') 
                FROM job_skills js 
                JOIN candidate_skills cs ON js.skill_id = cs.skill_id 
                JOIN skills s ON s.id = js.skill_id 
                WHERE js.job_id = j.id AND cs.candidate_id = c.id
            ) AS matched_skill_names,
            (
                SELECT COALESCE(string_agg(ct.trait, ', '), '') 
                FROM job_culture_keywords jck 
                JOIN candidate_traits ct ON jck.keyword = ct.trait 
                WHERE jck.job_id = j.id AND ct.candidate_id = c.id
            ) AS matched_trait_names
        FROM candidates c
        CROSS JOIN jobs j
    ) raw_matches
    WHERE matched_skills > 0;
    """

    avail_weights = {
        "Immediate": 1.0,
        "2 weeks": 0.7,
        "Not looking": 0.2
    }

    inserted_count = 0
    with conn.transaction():
        with conn.cursor(row_factory=dict_row) as cur:
            # Amendment 3: DELETE FROM matches first in the same transaction
            cur.execute("DELETE FROM matches;")

            cur.execute(match_query)
            rows = cur.fetchall()

            for row in rows:
                c_exp = float(row["candidate_exp"])
                j_min_exp = float(row["job_min_exp"])
                matched_skills = row["matched_skills"]
                total_skills = row["total_skills"]
                matched_culture = row["matched_culture"]
                total_culture = row["total_culture"]
                candidate_avail = row["candidate_avail"]
                matched_skill_names = row["matched_skill_names"]
                matched_trait_names = row["matched_trait_names"]

                skill_overlap = float(matched_skills) / float(total_skills) if total_skills > 0 else 0.0
                experience_fit = 1.0 if c_exp >= j_min_exp else (c_exp / j_min_exp if j_min_exp > 0 else 1.0)
                culture_overlap = float(matched_culture) / float(total_culture) if total_culture > 0 else 1.0
                availability_score = avail_weights.get(candidate_avail, 0.0)

                score = float(round(0.60 * skill_overlap + 0.25 * experience_fit + 0.10 * culture_overlap + 0.05 * availability_score, 4))

                skills_str = matched_skill_names if matched_skill_names else "none"
                traits_str = matched_trait_names if matched_trait_names else "none"
                reason = (
                    f"Matched {matched_skills}/{total_skills} required skills ({skills_str}). "
                    f"{c_exp:g} yrs exp vs {j_min_exp:g} yrs required. "
                    f"Culture fit: {matched_culture}/{total_culture} keywords ({traits_str}). "
                    f"Availability: {candidate_avail}."
                )

                cur.execute(
                    """
                    INSERT INTO matches (
                        job_id, candidate_id, score, skill_overlap, experience_fit, culture_overlap, availability_score, reason
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
                    """,
                    (
                        row["job_id"],
                        row["candidate_id"],
                        score,
                        skill_overlap,
                        experience_fit,
                        culture_overlap,
                        availability_score,
                        reason
                    )
                )
                inserted_count += 1

    return inserted_count

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

                # Amendment 3: Delete existing candidate_skills & candidate_traits for this entity before re-inserting
                cur.execute("DELETE FROM candidate_skills WHERE candidate_id = %s;", (cand_id,))
                cur.execute("DELETE FROM candidate_traits WHERE candidate_id = %s;", (cand_id,))

                # Amendment 4: Lowercase and strip skills/traits at ingestion
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

                # Amendment 3: Delete existing job_skills & job_culture_keywords for this entity before re-inserting
                cur.execute("DELETE FROM job_skills WHERE job_id = %s;", (job_id,))
                cur.execute("DELETE FROM job_culture_keywords WHERE job_id = %s;", (job_id,))

                # Amendment 4: Lowercase and strip required_skills/keywords at ingestion
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
