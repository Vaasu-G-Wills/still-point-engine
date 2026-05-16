"""
api/routes/generate.py — Script Generation SSE Endpoint
"""
import json
import asyncio
import threading
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class GenerateRequest(BaseModel):
    topic:        str
    project_id:   Optional[int] = None
    tts_voice:    Optional[str] = None
    word_by_word: bool = True
    llm_provider: str  = "local"   # "local" | "gemini"


@router.post("/generate")
async def generate_script(req: GenerateRequest):
    queue: asyncio.Queue = asyncio.Queue()
    loop  = asyncio.get_event_loop()

    def yield_callback(event: str, data):
        loop.call_soon_threadsafe(queue.put_nowait, {"type": event, "data": data})

    def run():
        try:
            from pipeline import run_pipeline
            output = run_pipeline(
                req.topic,
                yield_callback=yield_callback,
                tts_voice=req.tts_voice,
                llm_provider=req.llm_provider,
                render_video=False,
            )
            output["word_by_word"] = req.word_by_word

            # ── Update project phase ──────────────────────────────────────────
            if req.project_id:
                try:
                    from db import update_project_phase
                    update_project_phase(req.project_id, "script_done")
                except Exception:
                    pass

            loop.call_soon_threadsafe(queue.put_nowait, {
                "type": "complete",
                "data": output,
            })
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "data": str(e)})

    threading.Thread(target=run, daemon=True).start()

    async def event_stream():
        while True:
            event = await queue.get()
            payload = json.dumps(event, default=str)
            yield f"data: {payload}\n\n"
            if event["type"] in ("complete", "error"):
                break

    return StreamingResponse(event_stream(), media_type="text/event-stream")
