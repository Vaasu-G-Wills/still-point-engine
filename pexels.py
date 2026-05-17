"""
pexels.py — Pexels API integration for auto-fetching section backgrounds.

Free API: https://www.pexels.com/api/
Rate limits: 200 req/hour, 20,000 req/month (generous for our use case)

Contextual mode: each ~4-sentence chunk of the script gets its own image,
creating a visual story that follows the narration beat by beat.
"""
import os
import re
import json
import hashlib
import requests
import ollama
from config import LLM_MODEL

PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
PEXELS_PHOTO_URL  = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_URL  = "https://api.pexels.com/videos/search"

# Local cache directory for downloaded Pexels media
CACHE_DIR = os.path.join(os.path.dirname(__file__), ".pexels_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _headers():
    if not PEXELS_API_KEY:
        raise ValueError(
            "PEXELS_API_KEY is not set. "
            "Get a free key at https://www.pexels.com/api/ and set it in config.py."
        )
    return {"Authorization": PEXELS_API_KEY}


# ── Search ────────────────────────────────────────────────────────────────────

def search_photos(query: str, per_page: int = 9, orientation: str = "landscape") -> list[dict]:
    """
    Search Pexels for photos matching `query`.
    Returns a list of dicts with preview/download URLs.
    """
    r = requests.get(
        PEXELS_PHOTO_URL,
        headers=_headers(),
        params={"query": query, "per_page": per_page, "orientation": orientation},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    results = []
    for p in data.get("photos", []):
        results.append({
            "id":          p["id"],
            "photographer": p["photographer"],
            "preview_url": p["src"]["medium"],       # ~600px for UI preview
            "full_url":    p["src"]["large2x"],       # ~2560px for video BG
            "alt":         p.get("alt", ""),
            "width":       p["width"],
            "height":      p["height"],
        })
    return results


def search_videos(query: str, per_page: int = 6) -> list[dict]:
    """
    Search Pexels for videos matching `query`.
    Returns a list of dicts with preview poster + video file URLs.
    """
    r = requests.get(
        PEXELS_VIDEO_URL,
        headers=_headers(),
        params={"query": query, "per_page": per_page, "orientation": "landscape"},
        timeout=10,
    )
    r.raise_for_status()
    data = r.json()
    results = []
    for v in data.get("videos", []):
        # Pick the HD file (720p) if available, else first
        files = sorted(v.get("video_files", []), key=lambda f: f.get("height", 0), reverse=True)
        hd = next((f for f in files if f.get("height", 0) <= 720), files[0] if files else None)
        if not hd:
            continue
        results.append({
            "id":          v["id"],
            "preview_url": v.get("image", ""),         # thumbnail poster frame
            "video_url":   hd["link"],
            "width":       hd.get("width", 1280),
            "height":      hd.get("height", 720),
            "duration":    v.get("duration", 0),
        })
    return results


# ── Download & Cache ──────────────────────────────────────────────────────────

def download_photo(url: str, dest_dir: str = None, metadata: dict = None) -> str:
    """
    Downloads the photo at `url` into `dest_dir` (or CACHE_DIR).
    Returns the local file path. Uses a content-hash filename to deduplicate.
    If metadata is provided, it tracks the asset in the global library.
    """
    dest_dir = dest_dir or CACHE_DIR
    os.makedirs(dest_dir, exist_ok=True)

    # Hash the URL to create a stable filename
    ext = ".mp4" if (metadata and metadata.get("media_type") == "video") else ".jpg"
    fname = hashlib.md5(url.encode()).hexdigest() + ext
    fpath = os.path.join(dest_dir, fname)

    if not os.path.exists(fpath):
        r = requests.get(url, timeout=20, stream=True)
        r.raise_for_status()
        with open(fpath, "wb") as f:
            for chunk in r.iter_content(chunk_size=65536):
                f.write(chunk)
    
    if metadata:
        try:
            from db import track_pexels_asset
            track_pexels_asset(
                pexels_id    = metadata.get("id"),
                query        = metadata.get("query"),
                local_path   = fpath,
                preview_url  = metadata.get("preview_url"),
                photographer = metadata.get("photographer"),
                media_type   = metadata.get("media_type", "photo")
            )
        except Exception as e:
            print(f"[pexels] Failed to track asset: {e}")

    return fpath


# ── LLM Keyword Extractor ─────────────────────────────────────────────────────

def extract_search_query(section_name: str, section_text: str, topic: str, channel_template: str = "still_point") -> str:
    """
    Uses an LLM to distil the section text into a 1-2 word Pexels-optimised
    visual search query.
    """
    import llm_client
    from config import GEMINI_API_KEY
    
    is_zu = (channel_template == "zerourgency")
    
    if is_zu:
        instruction = "output a 1-2 word Pexels image search query that is a DIRECT, LITERAL, and CONCRETE representation of the subject. Avoid metaphors; if the text mentions a phone, search for 'smartphone'. If it mentions a city, search for 'cityscape'."
    else:
        instruction = "output a 1-2 word Pexels image search query that represents a tangible, physical metaphor for the theme."

    prompt = f"""You are a visual search expert. Given a section of a cinematic video script,
{instruction}

Topic: {topic}
Section: {section_name}
Text excerpt: {section_text[:1000]}

Rules:
- Output ONLY the 1-2 word search query, nothing else.
- Use only tangible, highly visual, common photographic nouns.
- The query MUST represent something physical that can be photographed.
- No punctuation, no quotes.

Search query:"""

    try:
        # Prefer Gemini for faster/smarter query extraction if key exists
        provider = "gemini" if GEMINI_API_KEY else "local"
        raw = llm_client.generate(prompt, provider=provider)
    except Exception as e:
        print(f"[pexels] LLM extraction failed ({provider}): {e}. Falling back to local...")
        raw = llm_client.generate(prompt, provider="local")
        
    raw = raw.strip().strip('"\'').strip()
    # Keep it clean — strip any leading labels the LLM might add
    raw = re.sub(r"(?i)^(search query|query)[:\s]+", "", raw).strip()
    return raw[:80]   # cap length


# ── Auto-Fetch Pipeline ───────────────────────────────────────────────────────

def auto_fetch_backgrounds(
    topic: str,
    sections: dict,
    dest_dir: str,
    use_videos: bool = False,
    channel_template: str = "still_point",
) -> dict:
    """
    For each of thesis / antithesis / synthesis:
      1. Extract a visual search query via LLM
      2. Search Pexels
      3. Download the best result
      4. Return a map of {section_name: local_file_path, ...}

    Also returns the search queries used so the UI can display them.
    """
    os.makedirs(dest_dir, exist_ok=True)

    targets = {
        "thesis":     sections.get("thesis", ""),
        "antithesis": sections.get("antithesis", ""),
        "synthesis":  sections.get("synthesis", ""),
    }

    results = {}   # section_name → local path
    queries = {}   # section_name → query string used

    for section_name, text in targets.items():
        if not text.strip():
            continue

        try:
            query = extract_search_query(section_name, text, topic, channel_template=channel_template)
            queries[section_name] = query
            print(f"[pexels] {section_name}: searching '{query}'")

            if use_videos:
                videos = search_videos(query, per_page=3)
                if not videos:
                    continue
                # Download just the poster frame for video BG (first frame image)
                best_vid = videos[0]
                local = download_photo(best_vid["preview_url"], dest_dir=dest_dir, metadata={
                    "id": best_vid["id"], "query": query, "preview_url": best_vid["preview_url"],
                    "media_type": "video"
                })
                results[section_name] = local
            else:
                photos = search_photos(query, per_page=5)
                if not photos:
                    continue
                best_photo = photos[0]
                local = download_photo(best_photo["full_url"], dest_dir=dest_dir, metadata={
                    "id": best_photo["id"], "query": query, "preview_url": best_photo["preview_url"],
                    "photographer": best_photo["photographer"], "media_type": "photo"
                })
                results[section_name] = local

        except Exception as e:
            print(f"[pexels] {section_name} failed: {e}")
            continue

    return {"paths": results, "queries": queries}


# ── Contextual Timeline Builder ───────────────────────────────────────────────

def split_into_chunks(text: str, sentences_per_chunk: int = 4) -> list[str]:
    """
    Splits a block of text into groups of ~sentences_per_chunk sentences.
    Each chunk becomes one visual moment in the video.
    """
    sentences = re.split(r'(?<=[.!?]) +', text.strip())
    sentences = [s.strip() for s in sentences if len(s.strip()) > 10]
    chunks = []
    for i in range(0, len(sentences), sentences_per_chunk):
        chunk = ' '.join(sentences[i : i + sentences_per_chunk])
        if chunk:
            chunks.append(chunk)
    return chunks or [text.strip()]


def build_contextual_timeline(
    node_name:           str,
    text:                str,
    topic:               str,
    dest_dir:            str,
    sentences_per_chunk: int = 4,
    channel_template:    str = "still_point",
) -> list[dict]:
    """
    Builds a contextual image timeline for ONE script node.
    Each chunk of sentences gets its own Pexels image.

    Returns a list of dicts:
        {
          'query':      str,   # Pexels search term used
          'path':       str,   # local file path to downloaded image
          'text_chunk': str,   # the text this image covers
          'char_count': int,   # proportional duration weight for video engine
        }
    """
    os.makedirs(dest_dir, exist_ok=True)
    chunks   = split_into_chunks(text, sentences_per_chunk)
    timeline = []

    for i, chunk in enumerate(chunks):
        try:
            query  = extract_search_query(f"{node_name} moment {i+1}", chunk, topic, channel_template=channel_template)
            print(f"[pexels] {node_name}[{i+1}/{len(chunks)}]: '{query}'")
            photos = search_photos(query, per_page=3)
            if not photos:
                photos = search_photos(f"{topic} cinematic", per_page=3)
            if photos:
                best_p = photos[0]
                path = download_photo(best_p["full_url"], dest_dir=dest_dir, metadata={
                    "id": best_p["id"], "query": query, "preview_url": best_p["preview_url"],
                    "photographer": best_p["photographer"], "media_type": "photo"
                })
                timeline.append({
                    "query":      query,
                    "path":       path,
                    "text_chunk": chunk,
                    "char_count": len(chunk),
                })
        except Exception as e:
            print(f"[pexels] {node_name}[{i+1}] error: {e}")
            # Repeat previous image to keep the timeline continuous
            if timeline:
                prev = dict(timeline[-1])
                prev["text_chunk"] = chunk
                prev["char_count"] = len(chunk)
                timeline.append(prev)

    return timeline


def build_full_contextual_script(
    topic:               str,
    sections:            dict,
    dest_dir:            str,
    sentences_per_chunk: int       = 4,
    nodes:               list[str] = None,
    channel_template:    str       = "still_point",
) -> dict:
    """
    Runs build_contextual_timeline for every node in the script.
    Returns { node_name: timeline_list, ... }
    """
    if nodes is None:
        nodes = list(sections.keys())

    result = {}
    for node in nodes:
        text = sections.get(node, "").strip()
        if not text:
            continue
        result[node] = build_contextual_timeline(
            node_name            = node,
            text                 = text,
            topic                = topic,
            dest_dir             = dest_dir,
            sentences_per_chunk  = sentences_per_chunk,
            channel_template     = channel_template,
        )
    return result
