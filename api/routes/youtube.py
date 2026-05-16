"""
api/routes/youtube.py — YouTube Metadata + Upload SSE Endpoints
"""
import json
import asyncio
import threading
import os
from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class MetadataRequest(BaseModel):
    topic:       str
    script_data: dict


@router.post("/yt/metadata")
def get_yt_metadata(req: MetadataRequest):
    from yt_research import generate_yt_metadata
    return generate_yt_metadata(req.topic, req.script_data)


@router.post("/yt/upload")
async def upload_to_youtube(
    video_path:  str           = Form(...),
    topic_dir:   str           = Form(...),
    title:       str           = Form(...),
    description: str           = Form(...),
    tags_json:   str           = Form(...),
    category_id: str           = Form("27"),
    privacy:     str           = Form("private"),
    language:    str           = Form("en"),
    playlist_id: str           = Form(""),
    hdd_path:    str           = Form(""),
    project_id:  str           = Form(""),
    channel_name:str           = Form("channel_1"),
    thumbnail:   Optional[UploadFile] = File(None),
):
    tags         = json.loads(tags_json)
    queue: asyncio.Queue = asyncio.Queue()
    loop         = asyncio.get_event_loop()

    # Save thumbnail if provided
    thumb_path = None
    if thumbnail and thumbnail.filename:
        thumb_path = os.path.join(topic_dir, "thumbnail.jpg")
        with open(thumb_path, "wb") as f:
            f.write(await thumbnail.read())

    def progress_callback(sent, total):
        loop.call_soon_threadsafe(queue.put_nowait, {
            "type":  "progress",
            "sent":  sent,
            "total": total,
        })

    def run():
        try:
            from yt_uploader import upload_video, upload_thumbnail, move_to_archive
            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "status",
                "data": "Authenticating with Google...",
            })

            result = upload_video(
                video_path=video_path,
                title=title,
                description=description,
                tags=tags,
                category_id=category_id,
                privacy=privacy,
                language=language,
                playlist_id=playlist_id.strip() or None,
                progress_callback=progress_callback,
                channel=channel_name,
            )

            if thumb_path:
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "status", "data": f"Setting thumbnail for {channel_name}...",
                })
                upload_thumbnail(result["video_id"], thumb_path, channel=channel_name)

            # Archive to HDD
            archive_path = None
            if hdd_path and hdd_path.strip() and os.path.isdir(hdd_path.strip()):
                loop.call_soon_threadsafe(queue.put_nowait, {
                    "type": "status", "data": "Moving to HDD archive...",
                })
                try:
                    archive_path = move_to_archive(topic_dir, hdd_path.strip())
                except Exception as mv_err:
                    result["archive_warning"] = str(mv_err)

            result["archive_path"] = archive_path

            # Update project phase to published
            pid = project_id.strip()
            if pid:
                try:
                    from db import update_project_phase
                    update_project_phase(
                        int(pid), "published",
                        yt_url=result.get("url"),
                        yt_video_id=result.get("video_id"),
                    )
                except Exception:
                    pass

            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "complete", "data": result,
            })

        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "error", "data": str(e),
            })

    threading.Thread(target=run, daemon=True).start()

    async def event_stream():
        while True:
            event = await queue.get()
            yield f"data: {json.dumps(event, default=str)}\n\n"
            if event["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
