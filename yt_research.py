"""
yt_research.py — YouTube Metadata Research Agent

Uses DuckDuckGo to discover ranking tags for the topic, then uses the local
LLM to craft a compelling title, description, relevant tags, and picks the
correct YouTube category. All processing is sequential and CPU-only.
"""
import re
import ollama
from config import LLM_MODEL
from duckduckgo_search import DDGS


# ─── YouTube Category Map ─────────────────────────────────────────────────────
# Full list of YouTube category IDs and their names.
# The LLM will choose the best fit using this reference.
YT_CATEGORIES = {
    "22": "People & Blogs",
    "23": "Comedy",
    "24": "Entertainment",
    "25": "News & Politics",
    "26": "Howto & Style",
    "27": "Education",
    "28": "Science & Technology",
    "29": "Nonprofits & Activism",
    "1":  "Film & Animation",
    "10": "Music",
}


# ─── DDG Tag Research ─────────────────────────────────────────────────────────

def research_yt_tags(topic: str, full_script: str = "", max_tags: int = 25) -> list[str]:
    """
    Searches DDG for YouTube-specific queries on the topic.
    Extracts frequent keywords from search results, then filters them for
    relevance against the actual script text so we don't upload junk tags.
    """
    search_queries = [
        f"{topic} documentary",
        f"{topic} philosophy explained",
        f"{topic} debate",
    ]

    raw_text = ""
    with DDGS() as ddgs:
        for q in search_queries:
            try:
                results = list(ddgs.text(q, max_results=5))
                for r in results:
                    raw_text += " " + r.get("title", "") + " " + r.get("body", "")
            except Exception:
                continue

    # Word frequency in DDG results
    words = re.findall(r'\b[A-Za-z][a-z]{2,}\b', raw_text)
    freq  = {}
    for w in words:
        w = w.lower()
        freq[w] = freq.get(w, 0) + 1

    stops = set(
        "the a an and or but if because as what when where how why is are was were be "
        "been have has had do does did will would can could may might must to of in for "
        "with on at from by about into like through after over between out against during "
        "without before under around among it its they their them we our you your this "
        "that also just very really even much many more most some such only both each "
        "every other same than then though still yet already often never always either "
        "neither whether however therefore thus hence moreover furthermore".split()
    )
    freq_tags = [
        w for w, c in sorted(freq.items(), key=lambda x: -x[1])
        if w not in stops and len(w) > 3 and c >= 2
    ]

    # ── Relevance filter ──────────────────────────────────────────────────────
    # Only keep a mined tag if it actually appears in the script content.
    # This prevents surfacing SEO terms that are topically unrelated.
    script_lower = full_script.lower() if full_script else ""
    verified_tags = [t for t in freq_tags if not script_lower or t in script_lower]

    # ── Structured base tags ──────────────────────────────────────────────────
    topic_words = topic.lower().split()
    structured = list(dict.fromkeys([
        topic.lower(),
        " ".join(topic_words[:3]) if len(topic_words) >= 3 else topic.lower(),
        f"{topic.lower()} explained",
        f"{topic.lower()} philosophy",
        "philosophy",
        "philosophical debate",
        "intellectual discourse",
        "thought experiment",
        "documentary",
        "deep discussion",
    ]))

    combined = structured + [t for t in verified_tags if t not in structured]
    return list(dict.fromkeys(combined))[:max_tags]


# ─── Category Picker ─────────────────────────────────────────────────────────

def pick_yt_category(topic: str, hook: str, synthesis: str) -> tuple[str, str]:
    """
    Uses the local LLM to select the most appropriate YouTube category for
    the video based on its content. Returns (category_id, category_name).
    """
    category_list = "\n".join([f"  {cid}: {name}" for cid, name in YT_CATEGORIES.items()])

    prompt = f"""
You are a YouTube content classifier. Choose the single best YouTube category for the following video.

TOPIC: {topic}
OPENING: {hook[:200]}
CONCLUSION: {synthesis[:200]}

AVAILABLE CATEGORIES:
{category_list}

Rules:
- Output ONLY the numeric category ID and nothing else.
- Example valid output: 27
- Do not explain. Do not add text. Output only the number.
"""
    res = ollama.generate(model=LLM_MODEL, prompt=prompt)
    category_id = re.search(r'\b(\d+)\b', res['response'].strip())

    if category_id and category_id.group(1) in YT_CATEGORIES:
        cid = category_id.group(1)
        return cid, YT_CATEGORIES[cid]

    # Fallback: Education
    return "27", "Education"


# ─── LLM Metadata Generator ───────────────────────────────────────────────────

def generate_yt_metadata(topic: str, script_data: dict) -> dict:
    """
    Generates a complete YouTube metadata package:
    title, description, relevant tags, best-fit category.
    """
    hook       = script_data.get("sections", {}).get("hook", "")
    synthesis  = script_data.get("sections", {}).get("synthesis", "")
    full_script = script_data.get("full_script", "")

    # ── Title ─────────────────────────────────────────────────────────────────
    title_prompt = f"""
You are a YouTube SEO expert. Generate ONE compelling YouTube video title.

TOPIC: {topic}
HOOK (opening line of the video): {hook[:300]}

Rules:
- Maximum 70 characters
- Must be intriguing and create curiosity — make the viewer NEED to watch
- Do NOT use clickbait words like "SHOCKING" or "YOU WON'T BELIEVE"
- Do NOT use the words "Thesis", "Antithesis", "Synthesis", "Dialectic"
- Do NOT add quotes, punctuation, or formatting
- Output ONLY the raw title text — nothing else, no prefix, no explanation
"""
    title_res = ollama.generate(model=LLM_MODEL, prompt=title_prompt)
    title = title_res['response'].strip().strip('"').strip("'")
    if len(title) > 70:
        title = title[:67] + "..."

    # ── Description ───────────────────────────────────────────────────────────
    desc_prompt = f"""
Write a YouTube video description for a philosophical debate video.

TOPIC: {topic}
HOOK: {hook[:300]}
CLOSING THOUGHT: {synthesis[:400]}

Rules:
- 3 short paragraphs max
- First paragraph: what the viewer will gain (2-3 sentences)
- Second paragraph: tease the three-part structure without using "thesis", "antithesis", "synthesis"
- Third paragraph: call to action (like, subscribe, comment their view)
- Natural, human writing — not a press release
- DO NOT add labels, headers, or bullet points
- Output only the description text — no preamble, no sign-off
"""
    desc_res    = ollama.generate(model=LLM_MODEL, prompt=desc_prompt)
    description = desc_res['response'].strip()

    # ── Category ──────────────────────────────────────────────────────────────
    category_id, category_name = pick_yt_category(topic, hook, synthesis)

    # ── Tags (script-verified) ────────────────────────────────────────────────
    tags = research_yt_tags(topic, full_script=full_script)

    return {
        "title":         title,
        "description":   description,
        "tags":          tags,
        "category_id":   category_id,
        "category_name": category_name,
        "language":      "en",
        "privacy":       "private",
    }
