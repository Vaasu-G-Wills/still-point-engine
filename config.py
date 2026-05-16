import os

# --- MODEL SETTINGS ---
LLM_MODEL = "llama3:8b"
EMBED_MODEL = "nomic-embed-text"

# --- PATHS ---
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))

# Primary output → external drive. Falls back to local output/ if drive isn't mounted.
_PRIMARY_OUTPUT = "/media/vaasu/Dev/StillPoint Videos"
OUTPUT_DIR = _PRIMARY_OUTPUT if os.path.isdir(_PRIMARY_OUTPUT) else os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CHROMA_DIR     = os.path.join(BASE_DIR, "chroma_storage")
SQLITE_DB_PATH = os.path.join(BASE_DIR, "engine_state.db")

# --- ENGINE SETTINGS ---
SIMILARITY_THRESHOLD = 0.999  # Tuned for padded 'nomic-embed-text' semantic clustering
DEBUG_MODE = False  # Mutated at runtime by flags

# --- THIRD-PARTY API KEYS ---
# Get a free Pexels API key at https://www.pexels.com/api/
# Paste your key below (or set as environment variable PEXELS_API_KEY)
PEXELS_API_KEY = "DYKXv8xx8qKVBCaKBDwhuJTB0UJ2cuFsY7Ysm0QTgCOBjq7EWuqGNhxB"

# Export so pexels.py can import from here instead of os.environ
if PEXELS_API_KEY:
    os.environ["PEXELS_API_KEY"] = PEXELS_API_KEY

# --- GEMINI API ---
# Get a free key at https://aistudio.google.com/app/apikey
GEMINI_API_KEY = "AIzaSyCnW-fqWiEmoWWKaIMV1hzTeYMoHytzdR0"          # paste your key here
GEMINI_MODEL   = "gemini-2.5-flash"   # or "gemini-1.5-pro" for higher quality

# --- CHANNEL BRANDING (used for intro / outro cards) ---
# Fill these in once — they're baked into every video's outro
CHANNEL_NAME   = "Still Point"          # e.g. "Still Point"
CHANNEL_HANDLE = "stillpointphilosophy" # e.g. "stillpointphilosophy" (no @)

# --- SPRINT 2: VIDEO STRUCTURE FEATURES ---
SHOW_INTRO_CARD    = False  # 4s animated topic title before first node
SHOW_TITLE_CARDS   = False  # 2.5s contextual title card between sections
SHOW_PROGRESS_BAR  = True   # thin progress bar at bottom of every frame
SHOW_OUTRO_CARD    = True   # 5s subscribe CTA at end
TITLE_CARD_SECS    = 2.5    # duration of each section title card
INTRO_CARD_SECS    = 4.0    # duration of opening title card
OUTRO_CARD_SECS    = 5.0    # duration of outro CTA card
MUSIC_DIR          = os.path.join(BASE_DIR, "music")   # folder for ambient tracks
MUSIC_VOLUME       = 0.14   # 0.0–1.0 mix level under narration
