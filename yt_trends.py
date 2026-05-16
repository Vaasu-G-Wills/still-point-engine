"""
yt_trends.py — YouTube Trending Topics Discovery

Uses the YouTube Data API v3 `videos.list(chart=mostPopular)` endpoint to
fetch trending videos in target categories, then uses the local LLM to extract
philosophical dialectic angles from the trending themes.

API cost: 1 quota unit per call (effectively free vs. 1,600 for upload).
All LLM processing is CPU-only.
"""
import os
import re
import ollama
from config import LLM_MODEL

# Categories to scan for philosophically relevant trending content
# We cross-reference multiple to find broader cultural conversations
TREND_CATEGORIES = {
    "25": "News & Politics",
    "27": "Education",
    "28": "Science & Technology",
    "22": "People & Blogs",
    "24": "Entertainment",
}

# Region codes to try (India first, then US for broader coverage)
REGION_CODES = ["IN", "US", "GB"]

# How many trending videos to pull per category
MAX_RESULTS_PER_CATEGORY = 10


# ─── YouTube Trending Fetcher ─────────────────────────────────────────────────

def fetch_trending_titles(youtube, region_code: str = "IN") -> list[dict]:
    """
    Fetches currently trending video titles and descriptions from YouTube
    across the target categories for a given region.
    Returns a list of {title, description, category, category_id} dicts.
    """
    all_videos = []

    for cat_id, cat_name in TREND_CATEGORIES.items():
        try:
            response = youtube.videos().list(
                part="snippet",
                chart="mostPopular",
                regionCode=region_code,
                videoCategoryId=cat_id,
                maxResults=MAX_RESULTS_PER_CATEGORY,
                fields="items(snippet(title,description,tags))",
            ).execute()

            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                all_videos.append({
                    "title":       snippet.get("title", ""),
                    "description": snippet.get("description", "")[:300],
                    "category":    cat_name,
                    "category_id": cat_id,
                })
        except Exception:
            # Some categories may not have trending in certain regions — skip silently
            continue

    return all_videos


def get_trending_raw(region_code: str = "IN") -> list[dict]:
    """
    Authenticates and fetches trending data.
    Falls back through region codes if one fails.
    """
    from yt_uploader import get_authenticated_service
    youtube = get_authenticated_service()

    videos = fetch_trending_titles(youtube, region_code)

    # If the primary region returns nothing, try fallbacks
    if not videos:
        for fallback in REGION_CODES:
            if fallback == region_code:
                continue
            videos = fetch_trending_titles(youtube, fallback)
            if videos:
                break

    return videos


# ─── LLM Topic Extractor ──────────────────────────────────────────────────────

def extract_dialectic_topics(trending_videos: list[dict], n_suggestions: int = 8) -> list[dict]:
    """
    Feeds the trending video titles to the local LLM and extracts
    N philosophical debate topics. Uses a simple pipe-delimited format
    to avoid complex parsing failures.
    """
    if not trending_videos:
        return []

    titles_block = "\n".join([
        f"[{v['category']}] {v['title']}"
        for v in trending_videos[:40]
    ])

    prompt = f"""You are a philosophical content strategist. Below are currently trending YouTube video titles.

TRENDING:
{titles_block}

Extract {n_suggestions} philosophical debate topics grounded in these trends.
Each topic must be a bold declarative claim (not a question) with genuine philosophical depth.

Output each topic on its own line using EXACTLY this format (pipe-separated, no extra text):
TOPIC | RATIONALE | CATEGORY

Example:
Convenience is eroding human agency | TikTok trends show passive consumption replacing deliberate choice | Science & Technology
Meritocracy is a myth that sustains inequality | Viral education debates reveal credential worship | Education

Now output {n_suggestions} lines in that exact format. Nothing else before or after."""

    res    = ollama.generate(model=LLM_MODEL, prompt=prompt)
    output = res['response'].strip()

    topics = []

    for line in output.split('\n'):
        line = line.strip()
        if not line:
            continue

        # Strip leading numbers/bullets like "1." "1)" "-" "*"
        line = re.sub(r'^[\d]+[.)]\s*', '', line)
        line = re.sub(r'^[-*•]\s*', '', line)

        # Try pipe-delimited format first
        if '|' in line:
            parts = [p.strip() for p in line.split('|')]
            if len(parts) >= 1 and len(parts[0]) > 10:
                topics.append({
                    "topic":     parts[0].strip(),
                    "rationale": parts[1].strip() if len(parts) > 1 else "",
                    "category":  parts[2].strip() if len(parts) > 2 else "General",
                })
            continue

        # Fallback: try labelled format (TOPIC: / Topic: / topic:)
        topic_m     = re.search(r'(?i)^topic[:\s]+(.+)', line)
        rationale_m = re.search(r'(?i)^rationale[:\s]+(.+)', line)
        category_m  = re.search(r'(?i)^category[:\s]+(.+)', line)

        if topic_m:
            topics.append({
                "topic":     topic_m.group(1).strip(),
                "rationale": "",
                "category":  "General",
            })
        elif rationale_m and topics:
            topics[-1]["rationale"] = rationale_m.group(1).strip()
        elif category_m and topics:
            topics[-1]["category"]  = category_m.group(1).strip()

    # Last resort: if still nothing parsed, treat each non-empty line as a raw topic
    if not topics:
        for line in output.split('\n'):
            line = line.strip()
            line = re.sub(r'^[\d]+[.)]\s*', '', line)
            line = re.sub(r'^[-*•]\s*', '', line)
            if len(line) > 15:
                topics.append({"topic": line, "rationale": "", "category": "General"})

    return topics[:n_suggestions]


# ─── Main Entry Point ─────────────────────────────────────────────────────────

def get_trending_topic_suggestions(
    region_code: str = "IN",
    n_suggestions: int = 8,
) -> dict:
    """
    Full pipeline: fetch YouTube trending → extract philosophical topics.
    Returns {topics: [...], region: str, raw_video_count: int}
    """
    raw_videos = get_trending_raw(region_code)

    if not raw_videos:
        return {
            "topics":          [],
            "region":          region_code,
            "raw_video_count": 0,
            "error":           "No trending data returned. Check API credentials or region code.",
        }

    topics = extract_dialectic_topics(raw_videos, n_suggestions=n_suggestions)

    return {
        "topics":          topics,
        "region":          region_code,
        "raw_video_count": len(raw_videos),
        "error":           None,
    }
