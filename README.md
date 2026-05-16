# The Still Point Engine

An automated, fully offline AI pipeline that generates high-fidelity, 2,000-word philosophical scripts structured around the **Hegelian Dialectic** (Hook → Thesis → Bridge → Antithesis → Bridge → Synthesis). The engine uses a reverse-RAG architecture via ChromaDB to prevent repetitive argumentation, local LLMs via Ollama for all inference, Kokoro for Text-to-Speech, and a FastAPI + React web UI for project management, video rendering, and YouTube publishing.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  React Frontend (Vite, port 5173)                       │
│  Projects Board │ Generator (Phase 1/2/3) │ Trends      │
└──────────────────────────┬──────────────────────────────┘
                           │ HTTP / SSE
┌──────────────────────────▼──────────────────────────────┐
│  FastAPI Backend (port 8000)                            │
│  /api/projects  /api/generate  /api/render-video        │
│  /api/yt/*      /api/trends    /api/voices              │
└──────────────────────────┬──────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        ▼                  ▼                  ▼
   Ollama (LLM)      Kokoro (TTS)       ChromaDB (RAG)
   llama3:8b         CPU-only           /chroma_storage
```

---

## Project-Based Workflow

Every video is a **Project** tracked through four phases:

| Phase | Meaning |
|---|---|
| `drafting` | Script is being generated |
| `script_done` | Script + audio complete |
| `video_done` | Video rendered, not yet published |
| `published` | Uploaded to YouTube |

The Projects board (`/projects`) shows all projects grouped by phase. Click any card to resume exactly where you left off.

---

## 1. Prerequisites

### System
```bash
sudo apt update && sudo apt install python3-pip python3-venv ffmpeg nodejs -y
```

### Ollama Models
```bash
ollama pull llama3:8b
ollama pull nomic-embed-text
```

### Python Environment
```bash
cd still_point_engine
python3 -m venv stillpoint_env
./stillpoint_env/bin/pip install -r requirements.txt
```

### Node.js (Frontend)
```bash
cd frontend
npm install
```

---

## 2. Running the App

### One command (recommended)
```bash
./start.sh
```
Starts both the FastAPI backend and the React frontend. Press `Ctrl+C` to stop both.

### Manual (two terminals)

**Terminal 1 — Backend:**
```bash
./stillpoint_env/bin/python server.py
```
API available at: `http://127.0.0.1:8000`  
API docs (Swagger): `http://127.0.0.1:8000/docs`

**Terminal 2 — Frontend:**
```bash
cd frontend && npm run dev
```
UI available at: `http://localhost:5173`

---

## 3. Pipeline Phases

### Phase 1 — Script & Audio Generation
- Select a topic (or pick one from the **Trending Topics** tab)
- Choose a TTS voice (Kokoro voices: `af_heart`, `bm_lewis`, `bm_george`, etc.) or skip audio
- The multi-agent pipeline streams output node-by-node in real time:
  `Hook → Thesis → Bridge → Antithesis → Bridge → Synthesis`
- Reverse-RAG blocks semantically similar past topics from recurring

### Phase 2 — Video Rendering
- Review the full script, source background images for each section
- Upload background images (Thesis / Antithesis / Synthesis)
- Renders a 720p video with DaVinci-style word-by-word subtitle highlighting
- Memory-safe: renders one node at a time to avoid OOM on limited hardware

### Phase 3 — YouTube Publishing
- Click **Research Metadata** — the LLM generates an SEO-optimised title, description, and relevant tags (cross-checked against the actual script content)
- An AI category picker selects the best YouTube category for the content
- Language is set to English (`en`) on both content and audio track
- Upload with configurable privacy (`private` / `unlisted` / `public`)
- Optional: move the folder to your HDD archive after upload

---

## 4. Trending Topics

The **Trending** tab fetches today's YouTube trending videos across:
- Education (27), News & Politics (25), Science & Technology (28), Entertainment (24), People & Blogs (22)

The local LLM extracts philosophical dialectic angles from trending titles. Click **Create project & generate** on any topic card to instantly create a project and drop into the Generator.

Supports regions: 🇮🇳 IN · 🇺🇸 US · 🇬🇧 GB · 🇦🇺 AU · 🇨🇦 CA

API cost: 5 quota units per fetch (vs 1,600 for upload — effectively free).

---

## 5. File Structure

```
still_point_engine/
├── server.py              # FastAPI entry point
├── start.sh               # One-command launcher
├── pipeline.py            # Multi-agent dialectic pipeline
├── video_engine.py        # 720p video renderer (memory-safe)
├── tts_engine.py          # Kokoro TTS wrapper
├── yt_uploader.py         # YouTube API upload + archive
├── yt_research.py         # SEO metadata + category picker
├── yt_trends.py           # YouTube trending topic discovery
├── reviewer.py            # Script quality reviewer
├── db.py                  # SQLite + ChromaDB init + CRUD
├── config.py              # Paths, model names, settings
├── prompts.py             # All LLM prompt templates
├── api/
│   └── routes/
│       ├── generate.py    # SSE: script generation
│       ├── video.py       # SSE: video rendering
│       ├── youtube.py     # SSE: YouTube upload
│       ├── projects.py    # Projects CRUD
│       ├── library.py     # Legacy script library
│       ├── trends.py      # Trending topics
│       └── voices.py      # Available TTS voices
├── frontend/              # React + Vite UI
│   └── src/
│       ├── pages/
│       │   ├── Projects.jsx   # Project board (home)
│       │   ├── Generator.jsx  # Phase 1/2/3 pipeline
│       │   ├── Library.jsx    # Script archive
│       │   └── Trends.jsx     # Trending topics
│       └── store/
│           └── pipeline.js    # Zustand global state
├── _streamlit_backup/     # Old Streamlit UI (backup)
├── output/                # Generated scripts, audio, video
├── chroma_storage/        # ChromaDB vector store
└── engine_state.db        # SQLite: projects + scripts
```

---

## 6. YouTube API Setup

1. Create a project in [Google Cloud Console](https://console.cloud.google.com)
2. Enable the **YouTube Data API v3**
3. Create **OAuth 2.0 credentials** (Desktop App type)
4. Download `client_secret.json` and place it in the project root
5. Add your Google account as a **Test User** in the OAuth consent screen
6. On first upload, a browser tab opens for consent — a `token.json` is saved for subsequent runs

**Quota usage:**
- Trending fetch: ~5 units
- Video upload: 1,600 units
- Daily quota: 10,000 units

---

## 7. Hardware Notes

- All LLM inference runs **CPU/GPU via Ollama** — no Python GPU code
- TTS (Kokoro) runs **CPU-only** to avoid VRAM conflicts
- Video rendering is **memory-safe** — nodes render to disk one at a time
- Tested on: GTX 1650 Ti, 16GB RAM, Ubuntu 24.04
