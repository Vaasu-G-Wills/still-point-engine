import sqlite3
import chromadb
from chromadb.utils import embedding_functions
from config import SQLITE_DB_PATH, CHROMA_DIR, EMBED_MODEL

# ─── Chroma embedding function ────────────────────────────────────────────────

class OllamaEmbeddingFunction(embedding_functions.EmbeddingFunction):
    def __init__(self, model_name: str):
        self.model_name = model_name
        import ollama
        self.ollama = ollama

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = []
        for text in input:
            res = self.ollama.embeddings(model=self.model_name, prompt=text)
            embeddings.append(res['embedding'])
        return embeddings


# ─── SQLite init ──────────────────────────────────────────────────────────────

def init_sqlite():
    conn = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()

    # Legacy scripts table (kept for backward compat)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS scripts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic TEXT NOT NULL,
            generation_date TEXT NOT NULL,
            status TEXT DEFAULT 'completed',
            file_path TEXT NOT NULL
        )
    ''')

    # Projects table — one row per video project
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS projects (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            topic            TEXT NOT NULL,
            folder_path      TEXT NOT NULL,
            phase            TEXT NOT NULL DEFAULT 'script_done',
            channel_template TEXT NOT NULL DEFAULT 'still_point',
            yt_url           TEXT,
            yt_video_id      TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')
    
    # Visual Asset Library — tracks every Pexels image/video used
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS pexels_assets (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            pexels_id    INTEGER UNIQUE,
            query        TEXT,
            local_path   TEXT NOT NULL,
            preview_url  TEXT,
            photographer TEXT,
            media_type   TEXT DEFAULT 'photo',
            created_at   TEXT NOT NULL DEFAULT (datetime('now'))
        )
    ''')

    conn.commit()

    # ── Auto-migrate old scripts into projects ────────────────────────────────
    _migrate_scripts_to_projects(conn)

    return conn


def _migrate_scripts_to_projects(conn):
    """
    One-time migration: for every row in `scripts` that has no corresponding
    project row (matched by folder_path), insert a project with phase inferred
    from what files are present on disk.
    """
    import os, json
    cursor = conn.cursor()

    cursor.execute('SELECT id, topic, generation_date, file_path FROM scripts')
    scripts = cursor.fetchall()

    for sid, topic, gen_date, file_path in scripts:
        folder_path = os.path.dirname(file_path)

        # Skip if already migrated
        cursor.execute('SELECT id FROM projects WHERE folder_path = ?', (folder_path,))
        if cursor.fetchone():
            continue

        if not os.path.exists(folder_path):
            continue

        # Infer phase from disk contents
        has_video = os.path.exists(os.path.join(folder_path, 'master_video.mp4'))
        phase     = 'video_done' if has_video else 'script_done'

        cursor.execute('''
            INSERT INTO projects (topic, folder_path, phase, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
        ''', (topic, folder_path, phase, gen_date, gen_date))

    conn.commit()


# ─── Chroma init ──────────────────────────────────────────────────────────────

def init_chroma():
    client    = chromadb.PersistentClient(path=CHROMA_DIR)
    embed_fn  = OllamaEmbeddingFunction(model_name=EMBED_MODEL)
    collection = client.get_or_create_collection(
        name="script_semantics",
        embedding_function=embed_fn,
        metadata={"hnsw:space": "cosine"},
    )
    return client, collection


def init_databases():
    init_sqlite()
    _, collection = init_chroma()
    return collection


# ─── Legacy scripts CRUD ──────────────────────────────────────────────────────

def insert_sqlite_record(topic: str, date_str: str, file_path: str):
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        'INSERT INTO scripts (topic, generation_date, file_path) VALUES (?, ?, ?)',
        (topic, date_str, file_path),
    )
    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_all_scripts():
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT id, topic, generation_date, file_path FROM scripts ORDER BY id DESC')
    rows   = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "topic": r[1], "date": r[2], "file_path": r[3]} for r in rows]


def delete_script(script_id: int):
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT file_path FROM scripts WHERE id = ?', (script_id,))
    row    = cursor.fetchone()

    if row:
        file_path  = row[0]
        import os, shutil
        parent_dir = os.path.dirname(file_path)
        base_name  = os.path.basename(parent_dir)

        if base_name != "output" and os.path.exists(parent_dir):
            shutil.rmtree(parent_dir)
        elif os.path.exists(file_path):
            os.remove(file_path)

        cursor.execute('DELETE FROM scripts WHERE id = ?', (script_id,))
        conn.commit()

        try:
            client     = chromadb.PersistentClient(path=CHROMA_DIR)
            collection = client.get_collection(
                name="script_semantics",
                embedding_function=OllamaEmbeddingFunction(model_name=EMBED_MODEL),
            )
            collection.delete(ids=[f"doc_{script_id}"])
        except Exception:
            pass

    conn.close()


# ─── Projects CRUD ────────────────────────────────────────────────────────────

def create_project(topic: str, folder_path: str, channel_template: str = "still_point") -> dict:
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO projects (topic, folder_path, phase, channel_template)
        VALUES (?, ?, 'drafting', ?)
    ''', (topic, folder_path, channel_template))
    pid = cursor.lastrowid
    conn.commit()
    conn.close()
    return get_project(pid)


def get_all_projects() -> list[dict]:
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, topic, folder_path, phase, channel_template, yt_url, yt_video_id, created_at, updated_at
        FROM projects ORDER BY updated_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [_project_row(r) for r in rows]


def get_project(project_id: int) -> dict | None:
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, topic, folder_path, phase, channel_template, yt_url, yt_video_id, created_at, updated_at
        FROM projects WHERE id = ?
    ''', (project_id,))
    row = cursor.fetchone()
    conn.close()
    return _project_row(row) if row else None


def update_project_phase(
    project_id: int,
    phase: str,
    yt_url: str = None,
    yt_video_id: str = None,
):
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE projects
        SET phase = ?, yt_url = COALESCE(?, yt_url),
            yt_video_id = COALESCE(?, yt_video_id),
            updated_at = datetime('now')
        WHERE id = ?
    ''', (phase, yt_url, yt_video_id, project_id))
    conn.commit()
    conn.close()


def delete_project(project_id: int):
    import os, shutil
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT folder_path FROM projects WHERE id = ?', (project_id,))
    row    = cursor.fetchone()
    if row and os.path.exists(row[0]):
        shutil.rmtree(row[0])
    cursor.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()


def _project_row(r) -> dict:
    import os, json
    project = {
        "id":          r[0],
        "topic":       r[1],
        "folder_path": r[2],
        "phase":            r[3],
        "channel_template": r[4],
        "yt_url":           r[5],
        "yt_video_id":      r[6],
        "created_at":       r[7],
        "updated_at":       r[8],
        "has_video":   False,
        "video_path":  None,
        "script_data": None,
    }
    folder = r[2]
    if os.path.exists(folder):
        vpath = os.path.join(folder, "master_video.mp4")
        project["has_video"]  = os.path.exists(vpath)
        project["video_path"] = vpath if project["has_video"] else None

        # Load script JSON for topic/word_count preview
        for fname in os.listdir(folder):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(folder, fname), "r") as f:
                        project["script_data"] = json.load(f)
                except Exception:
                    pass
                break
    return project

def track_pexels_asset(pexels_id, query, local_path, preview_url=None, photographer=None, media_type='photo'):
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT OR IGNORE INTO pexels_assets 
            (pexels_id, query, local_path, preview_url, photographer, media_type)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (pexels_id, query, local_path, preview_url, photographer, media_type))
        conn.commit()
    except Exception as e:
        print(f"[db] Error tracking asset: {e}")
    conn.close()

def get_pexels_library(limit=100):
    conn   = sqlite3.connect(SQLITE_DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM pexels_assets ORDER BY created_at DESC LIMIT ?', (limit,))
    rows = cursor.fetchall()
    conn.close()
    return [{
        "id": r[0], "pexels_id": r[1], "query": r[2], "local_path": r[3],
        "preview_url": r[4], "photographer": r[5], "media_type": r[6], "created_at": r[7]
    } for r in rows]
