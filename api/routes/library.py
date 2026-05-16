"""
api/routes/library.py — Script Library Endpoints
"""
import os
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/library")
def get_library():
    from db import get_all_scripts
    scripts = get_all_scripts()
    result  = []
    for s in scripts:
        entry = dict(s)
        # Load script JSON content inline
        try:
            with open(s["file_path"], "r", encoding="utf-8") as f:
                data = json.load(f)
            entry["script_data"]  = data
            topic_dir             = os.path.dirname(s["file_path"])
            entry["topic_dir"]    = topic_dir
            entry["has_video"]    = os.path.exists(os.path.join(topic_dir, "master_video.mp4"))
            entry["video_path"]   = os.path.join(topic_dir, "master_video.mp4") if entry["has_video"] else None
            audio_dir             = os.path.join(topic_dir, "audio")
            entry["audio_nodes"]  = []
            if os.path.exists(audio_dir):
                for node in ["hook", "thesis", "bridge_ab", "antithesis", "bridge_bc", "synthesis"]:
                    p = os.path.join(audio_dir, f"{node}.wav")
                    if os.path.exists(p):
                        entry["audio_nodes"].append({"node": node, "path": p})
        except Exception:
            pass
        result.append(entry)
    return result


@router.delete("/library/{script_id}")
def delete_library_entry(script_id: int):
    from db import delete_script
    delete_script(script_id)
    return {"ok": True}


@router.get("/audio/{path:path}")
async def serve_audio(path: str):
    from urllib.parse import unquote
    full_path = unquote(path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Audio not found")
    return FileResponse(full_path, media_type="audio/wav")


@router.get("/video-file/{path:path}")
async def serve_video_file(path: str):
    from urllib.parse import unquote
    full_path = unquote(path)
    if not os.path.exists(full_path):
        raise HTTPException(404, "Video not found")
    return FileResponse(full_path, media_type="video/mp4")
