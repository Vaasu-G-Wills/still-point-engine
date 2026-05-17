"""
aligner.py — WhisperX Forced Alignment (SOTA)
---------------------------------------------
Replaces the bespoke torchaudio implementation with the industry standard whisperx.
Performs Whisper transcription + Wav2Vec2 forced alignment.
Mapped back to original script using SequenceMatcher.

Strictly CPU-only to avoid GPU OOM on RTX 1650.
"""

import os
import json
import re
import logging
from difflib import SequenceMatcher

# Universal FFmpeg injection: ensure whisperx / pyannote subprocesses find imageio_ffmpeg
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    ffmpeg_dir = os.path.dirname(ffmpeg_exe)
    
    # Symlink/copy platform-specific binary to a standard 'ffmpeg' filename
    target_ffmpeg = os.path.join(ffmpeg_dir, "ffmpeg")
    if not os.path.exists(target_ffmpeg):
        try:
            os.symlink(os.path.basename(ffmpeg_exe), target_ffmpeg)
            print(f"[aligner] Created symlink for ffmpeg: {target_ffmpeg}")
        except Exception as sym_e:
            import shutil
            shutil.copy(ffmpeg_exe, target_ffmpeg)
            print(f"[aligner] Copied ffmpeg binary to standard filename: {target_ffmpeg}")
            
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
    print(f"[aligner] Injected imageio_ffmpeg path into PATH: {ffmpeg_dir}")
except Exception as path_e:
    print(f"[aligner] Failed to inject imageio_ffmpeg path: {path_e}")

import whisperx

logger = logging.getLogger(__name__)

# --- Lazy-loaded Models ---
_whisperx_model = None
_align_model = None
_align_metadata = None

def _get_whisperx_models():
    global _whisperx_model, _align_model, _align_metadata
    
    device = "cpu"
    compute_type = "int8"
    
    if _whisperx_model is None:
        logger.info("[aligner] Loading WhisperX base.en model on CPU...")
        _whisperx_model = whisperx.load_model("base.en", device, compute_type=compute_type)
        
    if _align_model is None:
        logger.info("[aligner] Loading WhisperX Wav2Vec2 alignment model...")
        _align_model, _align_metadata = whisperx.load_align_model(language_code="en", device=device)
        
    return _whisperx_model, _align_model, _align_metadata

def _scrub(text):
    return re.sub(r'[^\w\s]', '', text.lower()).strip()

def align_audio(wav_path: str, script_text: str, force: bool = False) -> list[dict]:
    """
    Uses WhisperX for state-of-the-art forced alignment.
    Returns: list of dicts with {"word": str, "start": float, "end": float}
    """
    if not wav_path or not os.path.exists(wav_path):
        return []

    json_path = os.path.splitext(wav_path)[0] + "_timestamps.json"
    if not force and os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                return json.load(f)
        except Exception:
            pass

    try:
        device = "cpu"
        w_model, a_model, a_metadata = _get_whisperx_models()
        
        logger.info(f"[aligner] Transcribing {os.path.basename(wav_path)} with WhisperX...")
        # 1. Transcribe
        audio = whisperx.load_audio(wav_path)
        result = w_model.transcribe(audio, batch_size=1)
        
        logger.info(f"[aligner] Aligning {os.path.basename(wav_path)} with Wav2Vec2...")
        # 2. Align (Forced Alignment to sub-100ms precision)
        result = whisperx.align(result["segments"], a_model, a_metadata, audio, device, return_char_alignments=False)
        
        # Extract word timestamps
        spoken_words = []
        for segment in result["segments"]:
            for word_info in segment.get("words", []):
                # Sometimes words might not have a start/end if they are silent or misaligned
                if "start" in word_info and "end" in word_info:
                    spoken_words.append({
                        "word": word_info["word"].strip(),
                        "start": round(word_info["start"], 3),
                        "end": round(word_info["end"], 3)
                    })

        if not spoken_words:
            logger.warning("[aligner] WhisperX found no alignable words.")
            return []

        # --- 3. Fuzzy Alignment to Script (Fixing Drift / Drift Mismatches) ---
        # Whisper might hallucinate or alter words. We force the timestamps 
        # back onto our literal script words so the subtitles look correct.
        script_words = script_text.split()
        final_timestamps = []
        
        spoken_clean = [_scrub(w["word"]) for w in spoken_words]
        script_clean = [_scrub(w) for w in script_words]

        sm = SequenceMatcher(None, script_clean, spoken_clean)
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag in ('equal', 'replace'):
                for i, j in zip(range(i1, i2), range(j1, j2)):
                    final_timestamps.append({
                        "word": script_words[i],
                        "start": spoken_words[j]["start"],
                        "end": spoken_words[j]["end"]
                    })

        # Cache results
        with open(json_path, "w") as f:
            json.dump(final_timestamps, f, indent=2)
        
        logger.info(f"[aligner] Successfully aligned {len(final_timestamps)} words.")
        return final_timestamps

    except Exception as e:
        logger.error(f"[aligner] WhisperX alignment failed: {e}")
        return []

def load_timestamps(wav_path: str) -> list[dict]:
    json_path = os.path.splitext(wav_path)[0] + "_timestamps.json"
    if os.path.exists(json_path):
        try:
            with open(json_path, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return []
