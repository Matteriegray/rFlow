-- Recruiter Bot PostgreSQL Schema

CREATE TABLE IF NOT EXISTS candidates (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) UNIQUE NOT NULL,
    experience_years NUMERIC(4, 1) NOT NULL CHECK (experience_years >= 0),
    availability VARCHAR(50) NOT NULL CHECK (availability IN ('Immediate', '2 weeks', 'Not looking')),
    quirk TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS jobs (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) UNIQUE NOT NULL,
    min_experience NUMERIC(4, 1) NOT NULL CHECK (min_experience >= 0),
    tagline TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS skills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS candidate_skills (
    candidate_id INT REFERENCES candidates(id) ON DELETE CASCADE,
    skill_id INT REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (candidate_id, skill_id)
);

CREATE TABLE IF NOT EXISTS job_skills (
    job_id INT REFERENCES jobs(id) ON DELETE CASCADE,
    skill_id INT REFERENCES skills(id) ON DELETE CASCADE,
    PRIMARY KEY (job_id, skill_id)
);

CREATE TABLE IF NOT EXISTS candidate_traits (
    candidate_id INT REFERENCES candidates(id) ON DELETE CASCADE,
    trait VARCHAR(100) NOT NULL,
    PRIMARY KEY (candidate_id, trait)
);

CREATE TABLE IF NOT EXISTS job_culture_keywords (
    job_id INT REFERENCES jobs(id) ON DELETE CASCADE,
    keyword VARCHAR(100) NOT NULL,
    PRIMARY KEY (job_id, keyword)
);

CREATE TABLE IF NOT EXISTS matches (
    id SERIAL PRIMARY KEY,
    job_id INT REFERENCES jobs(id) ON DELETE CASCADE,
    candidate_id INT REFERENCES candidates(id) ON DELETE CASCADE,
    score NUMERIC(5, 4) NOT NULL,
    skill_overlap NUMERIC(5, 4) NOT NULL,
    experience_fit NUMERIC(5, 4) NOT NULL,
    culture_overlap NUMERIC(5, 4) NOT NULL,
    availability_score NUMERIC(5, 4) NOT NULL,
    reason TEXT NOT NULL,
    calculated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT unique_job_candidate UNIQUE (job_id, candidate_id)
);

-- Foreign key & join table performance indexes
CREATE INDEX IF NOT EXISTS idx_candidate_skills_candidate ON candidate_skills(candidate_id);
CREATE INDEX IF NOT EXISTS idx_candidate_skills_skill ON candidate_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_job_skills_job ON job_skills(job_id);
CREATE INDEX IF NOT EXISTS idx_job_skills_skill ON job_skills(skill_id);
CREATE INDEX IF NOT EXISTS idx_candidate_traits_candidate ON candidate_traits(candidate_id);
CREATE INDEX IF NOT EXISTS idx_job_culture_keywords_job ON job_culture_keywords(job_id);
CREATE INDEX IF NOT EXISTS idx_matches_job_score ON matches(job_id, score DESC);
CREATE INDEX IF NOT EXISTS idx_matches_candidate_score ON matches(candidate_id, score DESC);
