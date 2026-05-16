"""
aligner.py — Forced Alignment Engine
-------------------------------------
Uses ctc-forced-aligner (MMS-300M) to produce exact word-level timestamps
from a Kokoro-generated .wav file and its corresponding transcript.

Output per audio file:
  word_timestamps.json  →  [{word, start, end}, ...]   (seconds, float)

Key design decisions:
  - Strictly CPU-only: protects 4GB VRAM on the RTX 1650.
  - Lazy-loads the MMS-300M model on first call (~300MB download, cached).
  - Saves timestamps alongside the .wav so the video engine never re-aligns.
  - Graceful fallback: any exception returns [] so callers can degrade safely.
  - Kokoro outputs 24 kHz audio; MMS-300M requires 16 kHz — resampled here.
"""

import os
import json
import re
import logging

logger = logging.getLogger(__name__)

# ─── Module-level lazy state ──────────────────────────────────────────────────
_alignment_model     = None
_alignment_tokenizer = None

TARGET_SR = 16_000   # MMS-300M requirement


def _load_model():
    """Lazy-load the MMS-300M alignment model onto CPU. Downloads once, then cached."""
    global _alignment_model, _alignment_tokenizer
    if _alignment_model is not None:
        return _alignment_model, _alignment_tokenizer

    logger.info("[aligner] Loading MMS-300M forced-alignment model (first use)…")
    from ctc_forced_aligner import load_alignment_model
    _alignment_model, _alignment_tokenizer = load_alignment_model(
        device="cpu",
        dtype="float32",
    )
    logger.info("[aligner] MMS-300M loaded.")
    return _alignment_model, _alignment_tokenizer


def _scrub_text(raw: str) -> str:
    """
    Strip non-spoken content from raw script text so the aligner only sees
    words that Kokoro actually voiced.
    """
    text = raw.strip()
    # Remove markdown bold/italic markers
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    # Remove bracketed labels like [Thesis], (Note:)
    text = re.sub(r"[\[\(][^\]\)]{0,60}[\]\)]", "", text)
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def align_audio(wav_path: str, text: str, force: bool = False) -> list[dict]:
    """
    Align `text` to the audio at `wav_path` using MMS-300M forced alignment.

    Returns a list of dicts:
        [{"word": str, "start": float, "end": float}, ...]
    where start/end are in seconds.

    Saves (and caches) the result as `word_timestamps.json` in the same
    directory as the .wav. Set `force=True` to bypass the cache.

    Falls back to [] on any error — callers should handle the empty case
    by degrading to syllable-based estimation.
    """
    if not wav_path or not os.path.exists(wav_path):
        logger.warning(f"[aligner] wav not found: {wav_path}")
        return []

    # ── Cache check ──────────────────────────────────────────────────────────
    json_path = os.path.splitext(wav_path)[0] + "_timestamps.json"
    if not force and os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            logger.info(f"[aligner] Cache hit: {json_path} ({len(data)} words)")
            return data
        except Exception as e:
            logger.warning(f"[aligner] Cache corrupt ({e}), re-aligning…")

    try:
        import torch
        import torchaudio
        from ctc_forced_aligner import (
            generate_emissions,
            get_alignments,
            get_spans,
            postprocess_results,
            preprocess_text,
        )

        # ── Load & resample audio ─────────────────────────────────────────
        model, tokenizer = _load_model()

        waveform, sr = torchaudio.load(wav_path)
        if sr != TARGET_SR:
            resampler = torchaudio.transforms.Resample(sr, TARGET_SR)
            waveform = resampler(waveform)

        # MMS-300M expects mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        waveform = waveform.to(dtype=torch.float32)

        # ── Prepare text ─────────────────────────────────────────────────
        clean = _scrub_text(text)
        if not clean:
            logger.warning("[aligner] Empty text after scrubbing.")
            return []

        # ── Forced alignment ─────────────────────────────────────────────
        emissions, stride = generate_emissions(model, waveform, batch_size=1)
        tokens_starred, text_starred = preprocess_text(clean, language="eng")
        segments, scores, blank_token = get_alignments(
            emissions, tokens_starred, tokenizer
        )
        spans = get_spans(tokens_starred, segments, blank_token)
        results = postprocess_results(text_starred, spans, stride, scores)

        # ── Convert to simple word/start/end dicts ────────────────────────
        timestamps = []
        for entry in results:
            word  = entry.get("text", "").strip()
            start = round(float(entry.get("start", 0.0)), 4)
            end   = round(float(entry.get("end",   0.0)), 4)
            if word:
                timestamps.append({"word": word, "start": start, "end": end})

        logger.info(
            f"[aligner] Aligned {len(timestamps)} words in "
            f"{os.path.basename(wav_path)}"
        )

        # ── Cache to disk ─────────────────────────────────────────────────
        with open(json_path, "w") as f:
            json.dump(timestamps, f, indent=2)

        return timestamps

    except Exception as e:
        logger.error(f"[aligner] Alignment failed for {wav_path}: {e}")
        return []


def load_timestamps(wav_path: str) -> list[dict]:
    """
    Load cached word timestamps for a wav file, if available.
    Returns [] if no cache exists (caller should fall back to syllable mode).
    """
    json_path = os.path.splitext(wav_path)[0] + "_timestamps.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []
