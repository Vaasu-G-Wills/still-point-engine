import json
import os
import re
import time
from datetime import datetime
import ollama   # still needed for embeddings fallback
import llm_client

from config import LLM_MODEL, SIMILARITY_THRESHOLD, OUTPUT_DIR
import config
import numpy as np
from db import init_databases, insert_sqlite_record, get_all_scripts
from prompts import (
    THESIS_PROMPT, ANTITHESIS_PROMPT, SYNTHESIS_PROMPT,
    EDITOR_PROMPT, EXCLUSION_HEADER, REWRITE_INSTRUCTION,
    HOOK_PROMPT, BRIDGE_AB_PROMPT, BRIDGE_BC_PROMPT,
    ZU_HOOK_PROMPT, ZU_CONTEXT_PROMPT, ZU_DEEP_DIVE_PROMPT, ZU_TAKEAWAY_PROMPT
)
from research import get_web_context
from reviewer import get_repetition_penalty

# Initialize Chromab memory store
collection = init_databases()

def check_topic_similarity_block(new_topic: str) -> str:
    """Check if the new topic is too semantically similar to past topics and block if it is."""
    past_scripts = get_all_scripts()
    if not past_scripts:
        return None
        
    past_topics = [s['topic'] for s in past_scripts]
    
    # Pad the topic for embedding to give Nomic more semantic surface area
    def pad_topic(t):
        return f"A philosophical Hegelian dialectic exploring the topic of: {t}"
    
    new_embed = llm_client.embed(pad_topic(new_topic))
    
    for past_topic in past_topics:
        # Check exact string match (case insensitive)
        if past_topic.lower() == new_topic.lower():
            return past_topic
            
        # Semantic check
        past_embed = llm_client.embed(pad_topic(past_topic))
        
        # Cosine similarity
        dot = sum(a * b for a, b in zip(new_embed, past_embed))
        norm_a = sum(a * a for a in new_embed) ** 0.5
        norm_b = sum(b * b for b in past_embed) ** 0.5
        similarity = dot / (norm_a * norm_b)
        
        if similarity >= config.SIMILARITY_THRESHOLD:
            return past_topic
            
    return None

def retrieve_exclusions(topic: str) -> list[str]:
    """Query ChromaDB for semantically similar past topics to enforce the Anti-Repetition Pipeline."""
    res = collection.query(
        query_texts=[topic],
        n_results=5
    )
    
    exclusions = []
    if res and "distances" in res and res["distances"]:
        distances = res["distances"][0]
        documents = res["documents"][0]
        
        for i, dist in enumerate(distances):
            # Chroma returns distance (e.g. cosine distance). Lower distance = higher similarity.
            # 1 - distance = cosine similarity
            similarity = 1.0 - dist
            if similarity >= config.SIMILARITY_THRESHOLD:
                exclusions.append(documents[i])
                
    return exclusions

def format_exclusion_block(exclusions: list[str]) -> str:
    if not exclusions:
        return ""
    constraints = "\n".join([f"- {ex}" for ex in exclusions])
    return EXCLUSION_HEADER.format(exclusions=constraints)

def clean_llm_conversational_filler(text: str) -> str:
    # Strip leading/trailing whitespace first
    text = text.strip()
    
    # Remove bracketed labels like [Rewritten Text], (Output:), **Revised:**
    text = re.sub(r'^[\[\(\*]+[^\]\)\*\n]{0,60}[\]\)\*]+\s*\n?', '', text, flags=re.IGNORECASE).strip()
    
    lines = text.split('\n')
    while lines and not lines[0].strip():
        lines.pop(0)
        
    while lines:
        first_line = lines[0].strip().lower()
        fillers = [
            "here is the", "here's the", "here's a", "here is a",
            "certainly", "sure", "of course", "absolutely",
            "rewritten text", "revised text", "edited text", "refined version",
            "here is an", "output:", "here are the",
            "hook:", "opening:", "bridge:", "transition:",
            "potential opening", "potential hook",
            "this could work", "grabbing attention",
            "here's my attempt", "here is my attempt", "attempt at rewriting",
            "elevate the prose", "remove ai slop", "revised version",
            "certainly! here is", "sure! here is",
        ]
        
        # Aggressive check for lines ending in colon that look like labels
        if (first_line.endswith(':') or first_line.endswith('：')) and len(first_line) < 150:
            if any(f in first_line for f in ["here is", "here's", "revised", "rewritten", "output", "script", "attempt"]):
                lines.pop(0)
                while lines and not lines[0].strip(): lines.pop(0)
                continue

        if any(f in first_line for f in fillers) and len(first_line) < 150:
            lines.pop(0)
            while lines and not lines[0].strip():
                lines.pop(0)
        else:
            break
            
    while lines:
        last_line = lines[-1].strip().lower()
        end_fillers = [
            "let me know", "i hope this", "feel free",
            "please note that", "note that i have", "as requested",
            "this script adheres", "i have avoided", "i have followed",
            "as per your", "as per the", "this meets your",
            "i hope this meets", "according to your", "in accordance with",
            "the script is designed", "i trust this",
        ]
        if any(f in last_line for f in end_fillers) and len(last_line) < 200:
            lines.pop()
            while lines and not lines[-1].strip():
                lines.pop()
        else:
            break
            
    return "\n".join(lines).strip()

def generate_node(prompt_template: str, kwargs: dict, provider: str = "local") -> str:
    """Execute one LLM call via the chosen provider (local Ollama or Gemini)."""
    target_words = 150 if config.DEBUG_MODE else 600
    if config.DEBUG_MODE and "target_words" not in kwargs:
        kwargs["target_words"] = target_words

    prompt = prompt_template.format(**kwargs)
    raw    = llm_client.generate(prompt, provider=provider)
    return clean_llm_conversational_filler(raw)

def run_pipeline(topic: str, yield_callback=None, **kwargs):
    """
    Executes the Dialectic Pipeline.
    yield_callback is an optional function for real-time UI updates.
    llm_provider kwarg: "local" (default) or "gemini"
    """
    provider = kwargs.get("llm_provider", "local")
    if yield_callback: yield_callback("status", "🔍 Checking past history for duplicates...")
    
    blocked_topic = check_topic_similarity_block(topic)
    if blocked_topic:
        if yield_callback: yield_callback("status", f"❌ BLOCKED: Topic is too similar to past script: '{blocked_topic}'")
        raise ValueError(f"Topic blocked: Too similar to existing generated video '{blocked_topic}'. AI slop prevented.")

    if yield_callback: yield_callback("status", "🔍 Retrieving Exclusions (Reverse RAG)...")
    exclusions = retrieve_exclusions(topic)
    exclusion_block = format_exclusion_block(exclusions)
    
    if yield_callback and exclusions:
        yield_callback("exclusions", exclusions)

    # Node 0: Research Agent
    if yield_callback: yield_callback("status", "🌐 Research Agent fetching fresh real-world context...")
    web_context = get_web_context(topic)

    script_format = kwargs.get("script_format", "still_point")
    is_zu = (script_format == "zerourgency")
    
    # Generate nodes based on format
    if is_zu:
        if yield_callback: yield_callback("status", "🎯 Generating Hook (ZeroUrgency)...")
        hook = generate_node(ZU_HOOK_PROMPT, {
            "topic": topic, "exclusion_block": exclusion_block, "target_words": 60 if config.DEBUG_MODE else 80
        }, provider)
        if yield_callback: yield_callback("hook", hook)

        if yield_callback: yield_callback("status", "📖 Generating Context...")
        context = generate_node(ZU_CONTEXT_PROMPT, {
            "topic": topic, "exclusion_block": exclusion_block, "web_context": web_context, "target_words": 150 if config.DEBUG_MODE else 400
        }, provider)
        if yield_callback: yield_callback("context", context)

        if yield_callback: yield_callback("status", "⚡ Generating Deep Dive...")
        deep_dive = generate_node(ZU_DEEP_DIVE_PROMPT, {
            "topic": topic, "exclusion_block": exclusion_block, "web_context": web_context, "target_words": 150 if config.DEBUG_MODE else 500
        }, provider)
        if yield_callback: yield_callback("deep_dive", deep_dive)

        if yield_callback: yield_callback("status", "⚖️ Generating Takeaway...")
        takeaway = generate_node(ZU_TAKEAWAY_PROMPT, {
            "topic": topic, "exclusion_block": exclusion_block, "web_context": web_context, "target_words": 150 if config.DEBUG_MODE else 350
        }, provider)
        if yield_callback: yield_callback("takeaway", takeaway)

        nodes_to_edit = [("Context", context), ("Deep_Dive", deep_dive), ("Takeaway", takeaway)]
    else:
        # Node Hook: Provocative Intro
        if yield_callback: yield_callback("status", "🎯 Generating Hook (Intro)...")
        hook = generate_node(HOOK_PROMPT, {
            "topic": topic, "exclusion_block": exclusion_block, "target_words": 60 if config.DEBUG_MODE else 80
        }, provider)
        if yield_callback: yield_callback("hook", hook)

        # Node A: Thesis
        if yield_callback: yield_callback("status", "🧠 Generating Node A (Thesis)...")
        thesis = generate_node(THESIS_PROMPT, {
            "topic": topic, "exclusion_block": exclusion_block, "web_context": web_context, "target_words": 150 if config.DEBUG_MODE else 600
        }, provider)
        if yield_callback: yield_callback("thesis", thesis)

        # Bridge A→B
        if yield_callback: yield_callback("status", "🔗 Generating Bridge A→B (Transition)...")
        bridge_ab = generate_node(BRIDGE_AB_PROMPT, {
            "topic": topic, "thesis_text": thesis
        }, provider)
        if yield_callback: yield_callback("bridge_ab", bridge_ab)

        # Node B: Antithesis
        if yield_callback: yield_callback("status", "⚡ Generating Node B (Antithesis)...")
        antithesis = generate_node(ANTITHESIS_PROMPT, {
            "topic": topic, "thesis_text": thesis, "exclusion_block": exclusion_block, "web_context": web_context, "target_words": 150 if config.DEBUG_MODE else 600
        }, provider)
        if yield_callback: yield_callback("antithesis", antithesis)

        # Bridge B→C
        if yield_callback: yield_callback("status", "🔗 Generating Bridge B→C (Transition)...")
        bridge_bc = generate_node(BRIDGE_BC_PROMPT, {
            "topic": topic
        }, provider)
        if yield_callback: yield_callback("bridge_bc", bridge_bc)

        # Node C: Synthesis
        if yield_callback: yield_callback("status", "⚖️ Generating Node C (Synthesis)...")
        synthesis = generate_node(SYNTHESIS_PROMPT, {
            "topic": topic, "thesis_text": thesis, "antithesis_text": antithesis,
            "exclusion_block": exclusion_block, "web_context": web_context, "target_words": 150 if config.DEBUG_MODE else 800
        }, provider)
        if yield_callback: yield_callback("synthesis", synthesis)
        
        nodes_to_edit = [("Thesis", thesis), ("Antithesis", antithesis), ("Synthesis", synthesis)]

    # Node D & E: The Editor Agent & Repetition Reviewer
    past_texts_buffer = ""
    final_nodes = {}
    
    for node_name, draft_text in nodes_to_edit:
        if yield_callback: yield_callback("status", f"🕵️ Editor Agent scrubbing AI Slop from {node_name}...")
        current_text = generate_node(EDITOR_PROMPT, {"draft_text": draft_text, "rewrite_prompt": ""}, provider)
        
        # Node E: Jaccard Sub-Loop
        attempts = 0
        while attempts < 3:
            score, banned = get_repetition_penalty(past_texts_buffer, current_text, n=2)
            if score > 0.15: # 15% repetition threshold
                attempts += 1
                if yield_callback: yield_callback("status", f"🔄 Reviewer blocked {node_name} ({score*100:.1f}% repeated logic). Forcing rewrite (Attempt {attempts}/3)...")
                
                banned_str = "\n".join([f"- {b}" for b in banned])
                rp = REWRITE_INSTRUCTION.format(banned_phrases=banned_str)
                current_text = generate_node(EDITOR_PROMPT, {"draft_text": draft_text, "rewrite_prompt": rp}, provider)
            else:
                break
                
        final_nodes[node_name.lower()] = current_text
        past_texts_buffer += " " + current_text
        if yield_callback: yield_callback(node_name.lower(), current_text)

    # Compile the final script sections
    sections = {"hook": hook}
    if is_zu:
        sections["context"]   = final_nodes["context"]
        sections["deep_dive"] = final_nodes["deep_dive"]
        sections["takeaway"]  = final_nodes["takeaway"]
        
        full_script = (
            f"{hook}\n\n"
            f"{sections['context']}\n\n"
            f"{sections['deep_dive']}\n\n"
            f"{sections['takeaway']}"
        )
    else:
        sections["thesis"]     = final_nodes["thesis"]
        sections["bridge_ab"]  = bridge_ab
        sections["antithesis"] = final_nodes["antithesis"]
        sections["bridge_bc"]  = bridge_bc
        sections["synthesis"]  = final_nodes["synthesis"]
        
        full_script = (
            f"{hook}\n\n"
            f"{sections['thesis']}\n\n"
            f"{bridge_ab}\n\n"
            f"{sections['antithesis']}\n\n"
            f"{bridge_bc}\n\n"
            f"{sections['synthesis']}"
        )

    # Unload Ollama explicitly from the GPU to make room for Kokoro TTS
    if yield_callback: yield_callback("status", "♻️ Freeing GPU Memory (Unloading Ollama)...")
    try:
        import urllib.request
        import json as json_lib
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=json_lib.dumps({"model": config.LLM_MODEL, "keep_alive": 0}).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        urllib.request.urlopen(req)
    except Exception:
        pass

    # Archive and Save - Topic Folder Structure
    if yield_callback: yield_callback("status", "💾 Archiving and Vectorizing...")
    
    word_count = len(full_script.split())
    
    timestamp = datetime.now().isoformat()
    date_str = datetime.now().strftime("%Y-%m-%d")
    safe_topic = topic.lower().replace(" ", "_").replace("/", "_")[:50]
    
    # Master Topic Directory
    topic_dir = os.path.join(OUTPUT_DIR, f"{date_str}_{safe_topic}")
    audio_dir = os.path.join(topic_dir, "audio")
    os.makedirs(audio_dir, exist_ok=True)
    
    json_filepath = os.path.join(topic_dir, "script.json")
    
    # Run TTS
    voice = kwargs.get('tts_voice', None)
    if voice:
        from tts_engine import generate_tts_audio
        if yield_callback: yield_callback("status", f"🎙️ Generating TTS Audio ({voice}) via Kokoro-82M...")
        
        from aligner import align_audio
        for section_name, section_text in sections.items():
            wav_path = os.path.join(audio_dir, f"{section_name}.wav")
            generate_tts_audio(section_text, voice, wav_path)
            # Generate word-level timestamps for robust highlighting
            if yield_callback: yield_callback("status", f"⏱️ Aligning {section_name}...")
            align_audio(wav_path, section_text)

    output_data = {
        "topic": topic,
        "generated_at": timestamp,
        "word_count": word_count,
        "exclusions_used": exclusions,
        "sections": sections,
        "full_script": full_script,
        "folder_path": topic_dir
    }

    with open(json_filepath, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    # SQLite
    record_id = insert_sqlite_record(topic, timestamp, json_filepath)
    
    # ChromaDB (Embedding the full generation mapped to the topic to catch future similarities)
    collection.add(
        documents=[full_script],
        metadatas=[{"topic": topic, "sqlite_id": record_id}],
        ids=[f"doc_{record_id}"]
    )
    
    render_video = kwargs.get('render_video', False)
    bg_image_bytes = kwargs.get('bg_image_bytes', {})
    
    # Save the bytes into the folder if they exist
    bg_paths = {}
    if bg_image_bytes:
        for node_n, bts in bg_image_bytes.items():
            bpath = os.path.join(topic_dir, f"bg_{node_n}.jpg")
            with open(bpath, "wb") as f:
                f.write(bts)
            bg_paths[node_n] = bpath
            
    if render_video and voice:
        import video_engine
        if yield_callback: yield_callback("status", "🎬 Stitching Final Master Video (Word-by-Word Mode)...")
        try:
            word_by_word = kwargs.get('word_by_word', True)
            subtitle_mode = kwargs.get('subtitle_mode', 'chunk')
            video_engine.build_master_video(
                topic_dir, output_data, 
                bg_images=bg_paths, 
                word_by_word=word_by_word,
                subtitle_mode=subtitle_mode
            )
        except Exception as ve:
            import traceback
            traceback.print_exc()
            if yield_callback: yield_callback("status", "⚠️ Video rendering failed. Output still saved.")
            
    # Generate Thumbnail
    try:
        from thumbnail_gen import generate_thumbnail
        if yield_callback: yield_callback("status", "🖼️ Generating Thumbnail...")
        generate_thumbnail(topic_dir, topic, hook)
    except Exception as e:
        if yield_callback: yield_callback("status", f"⚠️ Thumbnail gen failed: {e}")
    
    if yield_callback: yield_callback("status", "✅ Complete!")
    return output_data
