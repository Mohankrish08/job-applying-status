# Importing libraries
import math
from fastapi import FastAPI, HTTPException, Query, Request
import uvicorn
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import Any, Optional
from pydantic import BaseModel
import os
import pandas as pd

# from files
from logger import logger

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
JOBS_CSV_PATH = os.path.join(DATA_DIR, "applied_jobs.csv")
STATIC_DIR = os.path.join(BASE_DIR, "static")

# App Initializer
app = FastAPI(title="JOB Apply application", version="1.0")

# Configure CORS settings
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Models
class ResponseCls(BaseModel):
    IsSuccess: bool
    StatusMessage: str
    StatusObject: Optional[Any] = None

class ProcessJobRequest(BaseModel):
    company_name: str
    job_title: str
    website_url: Optional[str] = None

# Helper functions
def check_existing_job(company_name: str, job_title: str) -> ResponseCls:
    if not os.path.exists(JOBS_CSV_PATH):
        return ResponseCls(IsSuccess=True, StatusMessage="No existing jobs found", StatusObject=None)
    df = pd.read_csv(JOBS_CSV_PATH)
    existing_job = df[(df['company_name'] == company_name) & (df['job_title'] == job_title)]
    if not existing_job.empty:
        return ResponseCls(IsSuccess=False, StatusMessage="Job already exists", StatusObject=existing_job.to_dict(orient='records'))
    return ResponseCls(IsSuccess=True, StatusMessage="Job does not exist", StatusObject=None)

def save_job_to_csv(ProcessJobRequest: ProcessJobRequest) -> ResponseCls:
    job_data = {
        "company_name": ProcessJobRequest.company_name,
        "job_title": ProcessJobRequest.job_title,
        "website_url": ProcessJobRequest.website_url
    }
    df = pd.DataFrame([job_data])
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(JOBS_CSV_PATH):
        df.to_csv(JOBS_CSV_PATH, mode='a', header=False, index=False)
        logger.info(f"Job saved to CSV: {job_data}")
    else:
        df.to_csv(JOBS_CSV_PATH, index=False)
        logger.info(f"CSV file created and job saved: {job_data}")
    return ResponseCls(IsSuccess=True, StatusMessage="Job saved successfully", StatusObject=job_data)

# Endpoints
@app.get("/", include_in_schema=False)
def serve_ui():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/health")
def health_check():
    logger.info("Health check endpoint called")
    return {"IsSuccess": True, "StatusMessage": "Service is running", "StatusObject": None}


@app.post("/process-job")
async def process_job(request: ProcessJobRequest) -> ResponseCls:
    logger.info(f"Processing job for company: {request.company_name}, Job Title: {request.job_title}, Website: {request.website_url}")
    isThere = check_existing_job(request.company_name, request.job_title)
    if not isThere.IsSuccess:
        logger.warning(f"Job already exists: {isThere.StatusObject}")
        raise HTTPException(status_code=400, detail=isThere.StatusMessage)
    save_job_to_csv(request)
    return ResponseCls(IsSuccess=True, StatusMessage="Job processed successfully", StatusObject=None)

@app.get("/jobs")
async def get_jobs(
    page: int = Query(1, ge=1, description="1-indexed page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
):
    logger.info(f"Fetching jobs page={page} page_size={page_size}")
    if not os.path.exists(JOBS_CSV_PATH):
        logger.warning("No jobs found")
        empty = {"items": [], "page": 1, "page_size": page_size, "total_items": 0, "total_pages": 1}
        return ResponseCls(IsSuccess=True, StatusMessage="No jobs found", StatusObject=empty)

    df = pd.read_csv(JOBS_CSV_PATH).iloc[::-1].reset_index(drop=True)  # newest applied first
    total_items = len(df)
    total_pages = max(1, math.ceil(total_items / page_size))
    page = min(page, total_pages)  # clamp out-of-range page requests to the last page

    start = (page - 1) * page_size
    jobs_list = df.iloc[start:start + page_size].to_dict(orient='records')

    logger.info(f"Jobs fetched: page {page}/{total_pages}, {len(jobs_list)} of {total_items} items")
    return ResponseCls(
        IsSuccess=True,
        StatusMessage="Jobs fetched successfully",
        StatusObject={
            "items": jobs_list,
            "page": page,
            "page_size": page_size,
            "total_items": total_items,
            "total_pages": total_pages,
        },
    )

@app.delete("/jobs")
async def delete_job(company_name: str, job_title: str):
    logger.info(f"Deleting job for company: {company_name}, Job Title: {job_title}")
    if not os.path.exists(JOBS_CSV_PATH):
        raise HTTPException(status_code=404, detail="No jobs found")

    df = pd.read_csv(JOBS_CSV_PATH)
    mask = (df['company_name'] == company_name) & (df['job_title'] == job_title)
    if not mask.any():
        logger.warning(f"Job not found for deletion: {company_name} / {job_title}")
        raise HTTPException(status_code=404, detail="Job not found")

    df = df[~mask]
    df.to_csv(JOBS_CSV_PATH, index=False)
    logger.info(f"Job deleted: {company_name} / {job_title}")
    return ResponseCls(IsSuccess=True, StatusMessage="Job deleted successfully", StatusObject=None)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)