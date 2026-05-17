"""
api/routes/projects.py — Project CRUD Endpoints
"""
import os
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class CreateProjectRequest(BaseModel):
    topic:            str
    channel_template: str = "still_point"


class UpdatePhaseRequest(BaseModel):
    phase:       str
    yt_url:      Optional[str] = None
    yt_video_id: Optional[str] = None


@router.get("/projects")
def list_projects():
    from db import get_all_projects
    return get_all_projects()


@router.post("/projects")
def create_project(req: CreateProjectRequest):
    """
    Creates a new project record. The folder_path is provisionally set to
    the output directory — it will be updated to the real path after
    the pipeline creates the topic folder.
    """
    from db import create_project as db_create
    from config import OUTPUT_DIR
    import re, datetime
    # Generate a placeholder folder path (pipeline will create it)
    safe   = re.sub(r'[^\w\s-]', '', req.topic.lower())[:50].strip().replace(' ', '_')
    stamp  = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    folder = os.path.join(OUTPUT_DIR, f"{stamp}_{safe}")
    os.makedirs(folder, exist_ok=True)
    return db_create(req.topic, folder, channel_template=req.channel_template)


@router.get("/projects/{project_id}")
def get_project(project_id: int):
    from db import get_project as db_get
    p = db_get(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


@router.patch("/projects/{project_id}/phase")
def update_phase(project_id: int, req: UpdatePhaseRequest):
    from db import update_project_phase, get_project as db_get
    update_project_phase(project_id, req.phase, req.yt_url, req.yt_video_id)
    return db_get(project_id)


@router.delete("/projects/{project_id}")
def delete_project(project_id: int):
    from db import delete_project as db_del
    db_del(project_id)
    return {"ok": True}
