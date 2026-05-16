"""
title_gen.py — LLM-powered contextual section title generator.

Generates punchy, topic-specific chapter titles for each dialectic node,
replacing generic labels like "THESIS" with lines like:
  "The Illusion of Free Will"
  "Why Determinism Breaks Everything"
  "Reclaiming Agency in a Determined World"
"""
import re
import llm_client
from config import LLM_MODEL

# Friendly display names used as fallbacks
FALLBACK_TITLES = {
    "hook":       "Opening",
    "thesis":     "The Argument",
    "bridge_ab":  "The Turn",
    "antithesis": "The Challenge",
    "bridge_bc":  "The Resolution",
    "synthesis":  "The Synthesis",
}


def _generate_one_title(node_name: str, text: str, topic: str) -> str:
    """Ask the LLM for a short, punchy chapter title for this section."""
    prompt = f"""You are a philosophical documentary writer crafting chapter titles.
Given a section of a script, generate ONE short, punchy, evocative chapter title (4–8 words max).

Topic: {topic}
Section type: {node_name}
Text excerpt: {text[:500]}

Rules:
- Output ONLY the title, nothing else
- No quotes, no punctuation at the end
- Make it feel like a Netflix documentary chapter title
- Do NOT use the words "thesis", "antithesis", "synthesis", "hook"
- Should make a viewer lean forward and want to watch

Title:"""

    try:
        res = llm_client.generate(prompt)
        raw = res.strip().strip('"\'').strip()
        # Strip any leading label the LLM might add
        raw = re.sub(r"(?i)^(title|chapter)[:\s]+", "", raw).strip()
        # Cap length
        words = raw.split()
        if len(words) > 10:
            raw = " ".join(words[:9])
        return raw if len(raw) > 3 else FALLBACK_TITLES.get(node_name, node_name.replace("_", " ").title())
    except Exception as e:
        print(f"[title_gen] {node_name} failed: {e}")
        return FALLBACK_TITLES.get(node_name, node_name.replace("_", " ").title())


def generate_section_titles(topic: str, sections: dict) -> dict:
    """
    Generate LLM chapter titles for every non-empty section.

    Returns: { node_name: title_string, ... }

    Only generates titles for nodes that have a title card
    (hook, thesis, antithesis, synthesis — not bridges, which are transition).
    """
    title_nodes = ["hook", "thesis", "antithesis", "synthesis"]
    titles = {}

    for node in title_nodes:
        text = sections.get(node, "").strip()
        if not text:
            continue
        print(f"[title_gen] Generating title for: {node}")
        titles[node] = _generate_one_title(node, text, topic)
        print(f"[title_gen] → \"{titles[node]}\"")

    return titles


def identify_key_quotes(topic: str, sections: dict, max_quotes: int = 5) -> list:
    """
    Ask the LLM to pick the most quotable, self-contained sentences from the
    script for use as full-screen quote callout moments.

    Returns a list of verbatim (or near-verbatim) sentence strings.
    """
    all_text = " ".join(v for v in sections.values() if v.strip())
    if not all_text:
        return []

    prompt = f"""You are selecting powerful quotes for a philosophical documentary video.
From the script below, identify {max_quotes} of the most impactful, self-contained sentences
that would make compelling full-screen quote moments on screen.

Topic: {topic}
Script:
{all_text[:3500]}

Rules:
- Output ONLY the quotes, one per line, nothing else
- Each quote must be a verbatim sentence copied exactly from the script above
- Choose sentences that are: profound, self-contained, punchy, memorable
- Maximum 20 words per quote — skip long compound sentences
- Do NOT number them, add quotes, or add any labels

Quotes:"""

    try:
        res = llm_client.generate(prompt)
        raw = res.strip()
        quotes = [
            q.strip().strip('"\'""''').strip()
            for q in raw.split("\n")
            if q.strip() and len(q.strip()) > 10
        ]
        return quotes[:max_quotes]
    except Exception as e:
        print(f"[title_gen] identify_key_quotes failed: {e}")
        return []
