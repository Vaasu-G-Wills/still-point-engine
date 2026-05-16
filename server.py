"""
server.py — Still Point Engine FastAPI Server

Run with:
    ./stillpoint_env/bin/python server.py
"""
import sys
import os

# Ensure project root is on path for all existing modules
sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import generate, video, library, trends, youtube, voices, projects, browse, pexels_routes

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app):
    # Ensure all SQLite tables exist (creates projects table + migrates old scripts)
    from db import init_sqlite
    init_sqlite()
    yield

app = FastAPI(title="Still Point Engine API", version="2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(generate.router, prefix="/api")
app.include_router(video.router,    prefix="/api")
app.include_router(library.router,  prefix="/api")
app.include_router(trends.router,   prefix="/api")
app.include_router(youtube.router,  prefix="/api")
app.include_router(voices.router,   prefix="/api")
app.include_router(projects.router, prefix="/api")
app.include_router(browse.router,         prefix="/api")
app.include_router(pexels_routes.router,  prefix="/api")

# Serve built React bundle in production
frontend_dist = os.path.join(os.path.dirname(__file__), "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=True)
