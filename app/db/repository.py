import psycopg
from psycopg.rows import dict_row

def get_job_by_id(conn: psycopg.Connection, job_id: int) -> dict | None:
    """Fetch job by ID using parameterized SQL."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, title, min_experience, tagline FROM jobs WHERE id = %s;",
            (job_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "title": row["title"],
            "min_experience": float(row["min_experience"]),
            "tagline": row["tagline"]
        }

def get_candidate_by_id(conn: psycopg.Connection, candidate_id: int) -> dict | None:
    """Fetch candidate by ID using parameterized SQL."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT id, name, experience_years, availability, quirk FROM candidates WHERE id = %s;",
            (candidate_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": row["id"],
            "name": row["name"],
            "experience_years": float(row["experience_years"]),
            "availability": row["availability"],
            "quirk": row["quirk"]
        }

def get_matches_for_job(conn: psycopg.Connection, job_id: int) -> list[dict]:
    """
    Get ranked candidate matches for a job.
    Tie-break order: score DESC, availability_score DESC, candidate experience DESC, candidate id ASC.
    """
    query = """
    SELECT 
        c.id AS candidate_id,
        c.name AS candidate_name,
        m.score,
        m.skill_overlap,
        m.experience_fit,
        m.culture_overlap,
        m.availability_score,
        m.reason
    FROM matches m
    JOIN candidates c ON c.id = m.candidate_id
    WHERE m.job_id = %s
    ORDER BY m.score DESC, m.availability_score DESC, c.experience_years DESC, c.id ASC;
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (job_id,))
        rows = cur.fetchall()
        matches = []
        for r in rows:
            matches.append({
                "candidate_id": r["candidate_id"],
                "candidate_name": r["candidate_name"],
                "score": float(r["score"]),
                "skill_overlap": float(r["skill_overlap"]),
                "experience_fit": float(r["experience_fit"]),
                "culture_overlap": float(r["culture_overlap"]),
                "availability_score": float(r["availability_score"]),
                "reason": r["reason"]
            })
        return matches

def get_matches_for_candidate(conn: psycopg.Connection, candidate_id: int) -> list[dict]:
    """
    Get ranked job matches for a candidate.
    Tie-break order: score DESC, skill_overlap DESC, job min_experience DESC, job id ASC.
    """
    query = """
    SELECT 
        j.id AS job_id,
        j.title AS job_title,
        m.score,
        m.skill_overlap,
        m.experience_fit,
        m.culture_overlap,
        m.availability_score,
        m.reason
    FROM matches m
    JOIN jobs j ON j.id = m.job_id
    WHERE m.candidate_id = %s
    ORDER BY m.score DESC, m.skill_overlap DESC, j.min_experience DESC, j.id ASC;
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(query, (candidate_id,))
        rows = cur.fetchall()
        matches = []
        for r in rows:
            matches.append({
                "job_id": r["job_id"],
                "job_title": r["job_title"],
                "score": float(r["score"]),
                "skill_overlap": float(r["skill_overlap"]),
                "experience_fit": float(r["experience_fit"]),
                "culture_overlap": float(r["culture_overlap"]),
                "availability_score": float(r["availability_score"]),
                "reason": r["reason"]
            })
        return matches

def recompute_all_matches(conn: psycopg.Connection) -> int:
    """
    Recompute all candidate-job matches in a single transaction.
    Deletes existing matches first, calculates scores using SQL correlated subqueries,
    and inserts non-zero skill overlap matches.
    """
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
