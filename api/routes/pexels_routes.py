"""
api/routes/pexels_routes.py — Pexels search + auto-fetch endpoints
"""
import os
import tempfile
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


# ── Request / Response models ────────────────────────────────────────────────

class SearchRequest(BaseModel):
    query:       str
    per_page:    int  = 9
    media_type:  str  = "photo"   # "photo" | "video"

class AutoFetchRequest(BaseModel):
    topic:       str
    sections:    dict
    folder_path:      str
    use_videos:       bool = False
    channel_template: str  = "still_point"


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/pexels/search")
def pexels_search(req: SearchRequest):
    """
    Search Pexels for photos or videos matching `query`.
    Returns list of results with preview URLs (no download).
    """
    try:
        from pexels import search_photos, search_videos
        if req.media_type == "video":
            return {"results": search_videos(req.query, per_page=req.per_page)}
        return {"results": search_photos(req.query, per_page=req.per_page)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pexels/auto")
def pexels_auto(req: AutoFetchRequest):
    """
    Automatically selects and downloads the best Pexels photo for each section
    (thesis / antithesis / synthesis) using the local LLM to generate queries.
    Returns {section: local_path} mapping + the queries used.
    """
    if not req.folder_path or not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail="folder_path must be a valid directory")

    dest_dir = os.path.join(req.folder_path, "pexels_bg")
    try:
        from pexels import auto_fetch_backgrounds
        result = auto_fetch_backgrounds(
            topic=req.topic,
            sections=req.sections,
            dest_dir=dest_dir,
            use_videos=req.use_videos,
            channel_template=req.channel_template,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ContextualRequest(BaseModel):
    topic:               str
    sections:            dict
    folder_path:         str
    sentences_per_chunk: int  = 4
    channel_template:    str  = "still_point"


@router.post("/pexels/contextual")
def pexels_contextual(req: ContextualRequest):
    """
    Full contextual background generation:
    - Splits EVERY section into ~sentences_per_chunk sentence groups
    - LLM generates a unique visual search query per group
    - Downloads the best Pexels image per group
    - Returns a timeline per node: {node: [{query, path, text_chunk, char_count}, ...]}

    The timeline JSON can then be passed directly to /api/render-video as bg_timelines_json.
    """
    if not req.folder_path or not os.path.isdir(req.folder_path):
        raise HTTPException(status_code=400, detail="folder_path must be a valid directory")

    dest_dir = os.path.join(req.folder_path, "pexels_bg")
    try:
        from pexels import build_full_contextual_script
        timelines = build_full_contextual_script(
            topic               = req.topic,
            sections            = req.sections,
            dest_dir            = dest_dir,
            sentences_per_chunk = req.sentences_per_chunk,
            channel_template    = req.channel_template,
        )
        # Summary for UI display
        summary = {
            node: [
                {"query": item["query"], "char_count": item["char_count"]}
                for item in items
            ]
            for node, items in timelines.items()
        }
        return {"timelines": timelines, "summary": summary}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pexels/download")
def pexels_download(body: dict):
    """
    Downloads a single Pexels photo URL to the project folder.
    Returns the local file path.
    """
    url        = body.get("url", "").strip()
    folder_path = body.get("folder_path", "").strip()
    section    = body.get("section", "custom")

    if not url:
        raise HTTPException(status_code=400, detail="url is required")
    if not folder_path or not os.path.isdir(folder_path):
        raise HTTPException(status_code=400, detail="folder_path must be a valid directory")

    dest_dir = os.path.join(folder_path, "pexels_bg")
    try:
        from pexels import download_photo
        local_path = download_photo(url, dest_dir=dest_dir)
        return {"path": local_path, "section": section}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pexels/library")
def pexels_library(limit: int = 100):
    """Returns the history of all downloaded Pexels assets."""
    from db import get_pexels_library
    return {"library": get_pexels_library(limit=limit)}


@router.get("/pexels/key-status")
def pexels_key_status():
    """Returns whether the Pexels API key is configured."""
    key = os.environ.get("PEXELS_API_KEY", "")
    return {"configured": bool(key), "hint": "Set PEXELS_API_KEY in config.py or as env variable"}
