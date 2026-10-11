from pydantic import BaseModel

class JobMatchItem(BaseModel):
    candidate_id: int
    candidate_name: str
    score: float
    skill_overlap: float
    experience_fit: float
    culture_overlap: float
    availability_score: float
    reason: str

class JobMatchesResponse(BaseModel):
    job_id: int
    job_title: str
    matches: list[JobMatchItem]

class CandidateMatchItem(BaseModel):
    job_id: int
    job_title: str
    score: float
    skill_overlap: float
    experience_fit: float
    culture_overlap: float
    availability_score: float
    reason: str

class CandidateMatchesResponse(BaseModel):
    candidate_id: int
    candidate_name: str
    matches: list[CandidateMatchItem]

class SeedResponse(BaseModel):
    status: str
    candidates_seeded: int
    jobs_seeded: int
    matches_computed: int

class RecomputeResponse(BaseModel):
    status: str
    matches_computed: int
