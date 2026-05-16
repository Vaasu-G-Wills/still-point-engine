import os
import soundfile as sf
import numpy as np
import logging

logger = logging.getLogger(__name__)

# Lazy load the pipeline
_pipeline = None

# List of common Kokoro voices
AVAILABLE_VOICES = [
    "af_heart",
    "af_bella",
    "af_sarah",
    "am_adam",
    "am_michael",
    "bf_emma",
    "bf_isabella",
    "bm_george",
    "bm_lewis"
]

def get_pipeline():
    global _pipeline
    if _pipeline is None:
        from kokoro import KPipeline
        # We strictly force the TTS model onto the CPU. 
        # This prevents CUDA OutOfMemory (OOM) 
        # since Ollama and Streamlit are sharing the 4GB GTX 1650 Ti.
        _pipeline = KPipeline(lang_code='a', device='cpu')
    return _pipeline

def generate_tts_audio(text: str, voice: str, output_path: str):
    pipeline = get_pipeline()
    
    # The pipeline yields chunks. We split by newlines.
    generator = pipeline(text, voice=voice, speed=1.0, split_pattern=r'\n+')
    
    all_audio = []
    sample_rate = 24000
    
    for i, (gs, ps, audio) in enumerate(generator):
        if audio is not None:
            all_audio.append(audio)
            
    if all_audio:
        final_audio = np.concatenate(all_audio)
        sf.write(output_path, final_audio, sample_rate)

        # ── Forced alignment: run on CPU right after TTS ───────────────
        # Produces {output_path_without_ext}_timestamps.json for the video engine.
        try:
            from aligner import align_audio
            logger.info(f"[tts] Running forced alignment for {os.path.basename(output_path)}…")
            timestamps = align_audio(output_path, text)
            logger.info(f"[tts] Alignment complete: {len(timestamps)} word timestamps")
        except Exception as e:
            logger.warning(f"[tts] Forced alignment failed (will use syllable fallback): {e}")

        return True
    return False

