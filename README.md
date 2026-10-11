# Recruiter Bot

A small backend service that loads candidate profiles and job openings, scores every candidate against every job, and exposes ranked matches in both directions. Built for the RecruiterFlow backend take-home (Part 1 + Part 2).

**Stack:** Python 3.11+, FastAPI, PostgreSQL 16 (Docker), `psycopg` v3. All database access is hand-written, parameterized SQL. There is no ORM and no query builder.

## Run it locally

Requirements: Python 3.11+, Docker Desktop.

```bash
# 1. Install dependencies
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure
copy .env.example .env            # macOS/Linux: cp .env.example .env

# 3. Start Postgres (host port 5433 -> container 5432)
docker compose up -d
docker compose ps                 # wait until the service is "healthy"

# 4. Create the schema, load the seed data, compute matches
python run_seed.py

# 5. Start the API
python -m uvicorn app.main:app --port 8000
```

Any Postgres works instead of Docker: set `DATABASE_URL` in `.env` and run `app/db/schema.sql` yourself.

Expected row counts after seeding: candidates 15, jobs 6, skills 27, candidate_skills 50, job_skills 16, candidate_traits 30, job_culture_keywords 12, matches 31. Seeding is idempotent, so running it twice gives the same counts.

## API

```bash
# Ranked candidates for a job (job 1 = Backend Detective)
curl http://127.0.0.1:8000/jobs/1/matches

# Ranked jobs for a candidate (candidate 1 = Sherlock H.)
curl http://127.0.0.1:8000/candidates/1/matches

# Unknown id -> 404 {"detail": "Job with id 999 not found."}
curl -i http://127.0.0.1:8000/jobs/999/matches

# Reload seed data and recompute all matches
curl -X POST http://127.0.0.1:8000/seed

# Recompute matches only
curl -X POST http://127.0.0.1:8000/matches/recompute

# Interactive docs: http://127.0.0.1:8000/docs
```

On Windows PowerShell use `curl.exe` instead of `curl`.

Each match contains `score`, `skill_overlap`, `experience_fit`, `culture_overlap`, `availability_score` and a human-readable `reason`. Example, Backend Detective:

| Candidate | Score | Why |
|---|---|---|
| Sherlock H. | 0.95 | 3/3 skills, 8 yrs vs 3 required, culture 1/2 (analytical), immediate |
| Sheldon C. | 0.50 | 1/3 skills (pattern-recognition), experience met, no culture match, immediate |

## Schema

Hand-written in `app/db/schema.sql`:

- `candidates`, `jobs`: integer primary keys, `UNIQUE(name)` / `UNIQUE(title)` so seeding can upsert. A `CHECK` restricts availability to `Immediate`, `2 weeks`, `Not looking`.
- `skills` plus join tables `candidate_skills` and `job_skills`. Traits and culture keywords live in `candidate_traits` and `job_culture_keywords` with composite primary keys, so duplicates are impossible.
- `matches`: one row per (job, candidate) pair with the final score, each component, and the reason string. `UNIQUE(job_id, candidate_id)`.
- Indexes on the join-table foreign keys and on `matches(job_id, score DESC)` / `matches(candidate_id, score DESC)`.

## Matching algorithm and trade-offs

```
score = 0.60 * skill_overlap + 0.25 * experience_fit
      + 0.10 * culture_overlap + 0.05 * availability
```

- **skill_overlap** = matched required skills / required skills. Skills are the main signal, hence the heaviest weight. A candidate with **zero** overlap is excluded entirely, so nobody is recommended for a job they have no relevant skill for.
- **experience_fit** = 1.0 if the candidate meets the minimum, otherwise experience / minimum. Being under the bar is penalised proportionally. Being over it is not rewarded or penalised.
- **culture_overlap** = matched culture keywords / job keywords, comparing candidate traits to job culture keywords. It's a small weight because the data is thin and the match is exact-string only.
- **availability**: Immediate 1.0, 2 weeks 0.7, Not looking 0.2. It's a small weight and a soft signal: "Not looking" candidates stay in the results (visible in the reason) instead of being hidden.
- **Tie-breaks.** Job to candidates: score, then availability, then experience, then candidate id. Candidate to jobs: score, then skill overlap, then job minimum experience, then job id. Each ordering is deterministic.

**Where the work happens.** Counts (matched skills, required skills, matched culture keywords, and the matched names for the reason string) are computed in SQL with one correlated subquery per count. I avoided a single multi-join `GROUP BY` because each one-to-many join multiplies rows. Python only applies the weights and builds the reason text. Matches are precomputed into the `matches` table when seeding or on `POST /matches/recompute`. Reads are then simple indexed queries. The cost is staleness: if candidate or job data changes outside those endpoints, matches must be recomputed.

**Known limitations**
- Culture matching is exact string equality, so a keyword like `fast-paced` never matches any trait. A synonym map or embeddings would be the next step.
- Skills are a flat set: no proficiency levels, no skill synonyms.
- Seeding upserts by name/title and refreshes child rows, but does not delete candidates or jobs that were removed from the JSON file.
- There are no automated tests yet. I verified the scoring by hand and against the database (Sherlock 0.95 and Sheldon 0.50 for Backend Detective).

## Part 2: SQL Detective

The dataset is loaded as-is into its own `hiring_ops` schema so it stays independent of Part 1.

```bash
docker compose cp app/db/hiring_ops_setup.sql postgres:/tmp/setup.sql
docker compose exec postgres psql -U postgres -d rflow -f /tmp/setup.sql

docker compose cp sql_detective.sql postgres:/tmp/detective.sql
docker compose exec postgres psql -U postgres -d rflow -f /tmp/detective.sql
```

Answers are in `sql_detective.sql`, one query per question. Judgement calls:

- **Q2:** "reached Final" means a Final interview row exists, whatever the outcome. A LEFT JOIN keeps postings with zero.
- **Q3:** the same person can have several applicant ids (Ananya Rao, emails differing only by case). Identity is `LOWER(email)`, and "applied to a posting" means having an interview for it.
- **Q4:** conversion = passed Finals / total Finals, with `HAVING COUNT(*) >= 3`.
- **Q5:** `RANK() OVER (PARTITION BY department ...)` so ties are kept.
