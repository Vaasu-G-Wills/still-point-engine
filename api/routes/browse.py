"""
api/routes/browse.py — Filesystem Browser Endpoint

Lets the frontend navigate the local filesystem directory tree so
the user can pick a destination folder without typing a raw path.
"""
import os
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()


@router.get("/browse")
def browse_directory(path: str = Query(default="/")):
    """
    Returns the contents of `path` as a list of entries.
    Only directories are returned (files are irrelevant for folder picking).
    """
    path = os.path.expanduser(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    try:
        entries = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            if os.path.isdir(full) and not name.startswith('.'):
                entries.append({
                    "name": name,
                    "path": full,
                })

        parent = str(os.path.dirname(path)) if path != "/" else None

        return {
            "current": path,
            "parent":  parent,
            "entries": entries,
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")


@router.post("/projects/{project_id}/move")
def move_project(project_id: int, body: dict):
    """
    Moves the project folder to `destination` and updates folder_path in DB.
    """
    import shutil
    from db import get_project, update_project_phase
    import sqlite3
    from config import SQLITE_DB_PATH

    destination = body.get("destination", "").strip()
    if not destination:
        raise HTTPException(status_code=400, detail="destination is required")
    if not os.path.isdir(destination):
        raise HTTPException(status_code=400, detail=f"Destination not found: {destination}")

    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    src         = project["folder_path"]
    folder_name = os.path.basename(src.rstrip("/"))
    dest        = os.path.join(destination, folder_name)

    if os.path.exists(dest):
        dest = dest + "_moved"

    try:
        shutil.move(src, dest)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # Update folder_path in DB
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.execute(
        "UPDATE projects SET folder_path = ?, updated_at = datetime('now') WHERE id = ?",
        (dest, project_id),
    )
    conn.commit()
    conn.close()

    return {"ok": True, "new_path": dest}
