"""
api/routes/voices.py — TTS Voice List Endpoint
"""
from fastapi import APIRouter

router = APIRouter()

@router.get("/voices")
def get_voices():
    from tts_engine import AVAILABLE_VOICES
    return {"voices": AVAILABLE_VOICES}
