from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
import psycopg

from app.db.connection import get_pool, close_pool, get_db
from app.db import repository
from app.services.seed import seed_data
from app.models.match import (
    JobMatchesResponse,
    CandidateMatchesResponse,
    SeedResponse,
    RecomputeResponse
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Open connection pool on application startup
    get_pool()
    yield
    # Close connection pool on application shutdown
    close_pool()

app = FastAPI(
    title="Recruiter Bot API",
    description="Backend service for matching candidates and jobs using parameterized SQL and weighted scoring.",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/jobs/{id}/matches", response_model=JobMatchesResponse)
def get_job_matches(id: int, conn: psycopg.Connection = Depends(get_db)):
    """
    Get ranked candidate matches for a job opening.
    Returns 404 if the job does not exist.
    """
    job = repository.get_job_by_id(conn, id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with id {id} not found."
        )

    matches = repository.get_matches_for_job(conn, id)
    return {
        "job_id": job["id"],
        "job_title": job["title"],
        "matches": matches
    }

@app.get("/candidates/{id}/matches", response_model=CandidateMatchesResponse)
def get_candidate_matches(id: int, conn: psycopg.Connection = Depends(get_db)):
    """
    Get ranked job matches for a candidate.
    Returns 404 if the candidate does not exist.
    """
    candidate = repository.get_candidate_by_id(conn, id)
    if not candidate:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Candidate with id {id} not found."
        )

    matches = repository.get_matches_for_candidate(conn, id)
    return {
        "candidate_id": candidate["id"],
        "candidate_name": candidate["name"],
        "matches": matches
    }

@app.post("/seed", response_model=SeedResponse)
def run_seed(conn: psycopg.Connection = Depends(get_db)):
    """
    Idempotently seed database from docs/seed-data.json and recompute all matches.
    """
    result = seed_data(conn)
    return result

@app.post("/matches/recompute", response_model=RecomputeResponse)
def recompute_matches_endpoint(conn: psycopg.Connection = Depends(get_db)):
    """
    Recompute all candidate-job matches.
    """
    count = repository.recompute_all_matches(conn)
    return {
        "status": "success",
        "matches_computed": count
    }
