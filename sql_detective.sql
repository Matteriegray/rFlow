-- Part 2: SQL Detective Challenge
-- Run after db/hiring_ops_setup.sql (tables live in the hiring_ops schema).
SET search_path TO hiring_ops;

-- Q1: All currently open job postings with the owning recruiter's name.
SELECT jp.id AS job_posting_id,
       jp.title,
       jp.department,
       r.name AS recruiter_name
FROM job_postings jp
JOIN recruiters r ON r.id = jp.recruiter_id
WHERE jp.status = 'open'
ORDER BY jp.id;

-- Q2: For each job posting, how many applicants reached the Final stage?
-- "Reached" = has a Final interview row, whatever its outcome.
-- LEFT JOIN keeps postings with zero Final-stage applicants (shown as 0).
SELECT jp.id AS job_posting_id,
       jp.title,
       COUNT(DISTINCT i.applicant_id) AS applicants_at_final
FROM job_postings jp
LEFT JOIN interviews i
       ON i.job_posting_id = jp.id
      AND i.stage = 'Final'
GROUP BY jp.id, jp.title
ORDER BY jp.id;

-- Q3: People who effectively applied to more than one job posting.
-- The same person can appear under several applicant ids (e.g. Ananya Rao,
-- emails differing only by case), so identity is the lower-cased email.
-- A person "applied" to a posting if they have an interview for it.
SELECT LOWER(a.email) AS person_email,
       MIN(a.full_name) AS full_name,
       COUNT(DISTINCT i.job_posting_id) AS postings_applied_to
FROM applicants a
JOIN interviews i ON i.applicant_id = a.id
GROUP BY LOWER(a.email)
HAVING COUNT(DISTINCT i.job_posting_id) > 1
ORDER BY person_email;

-- Q4: Final-stage conversion rate per recruiter (passed / total Finals),
-- only for recruiters with at least 3 Final-stage interviews.
SELECT r.id AS recruiter_id,
       r.name AS recruiter_name,
       COUNT(*) AS final_interviews,
       COUNT(*) FILTER (WHERE i.outcome = 'passed') AS finals_passed,
       ROUND(100.0 * COUNT(*) FILTER (WHERE i.outcome = 'passed') / COUNT(*), 1)
           AS conversion_rate_pct
FROM interviews i
JOIN job_postings jp ON jp.id = i.job_posting_id
JOIN recruiters r ON r.id = jp.recruiter_id
WHERE i.stage = 'Final'
GROUP BY r.id, r.name
HAVING COUNT(*) >= 3
ORDER BY r.id;

-- Q5 (Bonus): Recruiter with the most successful placements (Final passed)
-- per department, using a window function. RANK keeps ties.
WITH placements AS (
    SELECT jp.department,
           r.id AS recruiter_id,
           r.name AS recruiter_name,
           COUNT(*) AS placements
    FROM interviews i
    JOIN job_postings jp ON jp.id = i.job_posting_id
    JOIN recruiters r ON r.id = jp.recruiter_id
    WHERE i.stage = 'Final' AND i.outcome = 'passed'
    GROUP BY jp.department, r.id, r.name
),
ranked AS (
    SELECT *,
           RANK() OVER (PARTITION BY department ORDER BY placements DESC) AS rnk
    FROM placements
)
SELECT department, recruiter_id, recruiter_name, placements
FROM ranked
WHERE rnk = 1
ORDER BY department;