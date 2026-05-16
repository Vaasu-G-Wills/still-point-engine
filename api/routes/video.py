"""
api/routes/video.py — Video Rendering SSE Endpoint
"""
import json
import asyncio
import threading
import os
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse, FileResponse
from fastapi import HTTPException
from typing import Optional
from urllib.parse import unquote
import glob
import shutil
from pydantic import BaseModel

router = APIRouter()

# Global state for tracking video rendering cancellation
CANCEL_FLAGS = {}

class CancelRequest(BaseModel):
    topic_dir: str

@router.post("/cancel-render")
async def cancel_render(req: CancelRequest):
    CANCEL_FLAGS[req.topic_dir] = True
    return {"status": "cancelled"}



@router.post("/render-video")
async def render_video(
    topic_dir:          str           = Form(...),
    script_json:        str           = Form(...),
    subtitle_mode:      str           = Form("chunk"),
    project_id:         str           = Form(""),
    # Uploaded image files (manual upload)
    bg_thesis:          Optional[UploadFile] = File(None),
    bg_antithesis:      Optional[UploadFile] = File(None),
    bg_synthesis:       Optional[UploadFile] = File(None),
    # Server-side paths (from Pexels auto-fetch / download)
    bg_thesis_path:     str           = Form(""),
    bg_antithesis_path: str           = Form(""),
    bg_synthesis_path:  str           = Form(""),
    # Contextual timeline JSON (from /api/pexels/contextual)
    bg_timelines_json:  str           = Form(""),
):
    script_data = json.loads(script_json)
    mode        = subtitle_mode.lower()
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # Reset the cancel flag for this project directory
    CANCEL_FLAGS[topic_dir] = False

    # Parse contextual timelines if provided
    bg_timelines = {}
    if bg_timelines_json.strip():
        try:
            bg_timelines = json.loads(bg_timelines_json)
        except Exception:
            pass

    # Build bg_images map — uploaded file takes priority over server path
    # (only used if bg_timelines is empty or doesn't cover a node)
    bg_images = {}
    path_overrides = {
        "thesis":     bg_thesis_path.strip(),
        "antithesis": bg_antithesis_path.strip(),
        "synthesis":  bg_synthesis_path.strip(),
    }
    for node_key, upload in [
        ("thesis",     bg_thesis),
        ("antithesis", bg_antithesis),
        ("synthesis",  bg_synthesis),
    ]:
        if upload and upload.filename:
            bpath = os.path.join(topic_dir, f"bg_{node_key}.jpg")
            with open(bpath, "wb") as f:
                f.write(await upload.read())
            bg_images[node_key] = bpath
        elif path_overrides.get(node_key) and os.path.exists(path_overrides[node_key]):
            bg_images[node_key] = path_overrides[node_key]



    def progress_callback(current, total, message):
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type":    "progress",
            "current": current,
            "total":   total,
            "message": message,
        })

    def run():
        def check_cancel():
            return CANCEL_FLAGS.get(topic_dir, False)

        try:
            import video_engine
            video_engine.ensure_font()
            out_path = video_engine.build_master_video(
                topic_dir, script_data,
                bg_images    = bg_images,
                bg_timelines = bg_timelines,
                subtitle_mode = mode,
                progress_callback=progress_callback,
                check_cancel=check_cancel,
            )
            # Update project phase
            pid = project_id.strip()
            if pid:
                try:
                    from db import update_project_phase
                    update_project_phase(int(pid), "video_done")
                except Exception:
                    pass
            loop.call_soon_threadsafe(queue.put_nowait, {
                "type":       "complete",
                "video_path": out_path,
            })
        except video_engine.RenderCancelledException as e:
            # Clean up partial render files from _tmp and master
            tmp_dir = os.path.join(topic_dir, "_tmp")
            if os.path.exists(tmp_dir):
                shutil.rmtree(tmp_dir, ignore_errors=True)
            master_path = os.path.join(topic_dir, "master_video.mp4")
            if os.path.exists(master_path):
                os.remove(master_path)
                
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "data": "Render cancelled by user."})
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "data": str(e)})

    threading.Thread(target=run, daemon=True).start()

    async def event_stream():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/video-file/{path:path}")
async def serve_video_file(path: str):
    """Serve a rendered video file by absolute path."""
    full_path = unquote(path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Video not found")
    return FileResponse(full_path, media_type="video/mp4")
