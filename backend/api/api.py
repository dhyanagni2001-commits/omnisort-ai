# FastAPI REST + WebSocket server.
# All endpoints bind to 127.0.0.1 by default, so open CORS is acceptable.

import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.database import db
from backend.watcher.file_watcher import event_queue
from backend.metrics.metrics import metrics
from backend.embeddings.embedding import embed_text, cosine_similarity

app = FastAPI(title="OmniSort AI", version="1.0.0")

# Allow all origins — safe because the server only listens on localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tracks all currently open WebSocket connections for broadcasting file events.
active_connections: list[WebSocket] = []


@app.on_event("startup")
def on_startup():
    # Ensure the SQLite schema exists before the first request arrives.
    db.init_db()


@app.get("/api/health")
def health():
    """Liveness probe — used by Docker health checks and uptime monitors."""
    return {"status": "ok"}


@app.get("/api/stats")
def stats():
    """Return aggregate file counts: total, duplicates, sensitive, and per-category."""
    return db.get_stats()


@app.get("/api/files")
def files(limit: int = 50, offset: int = 0):
    """Paginated file history ordered by most recently processed."""
    return db.get_files(limit=limit, offset=offset)


@app.get("/api/metrics")
def get_metrics():
    """Return the current observability snapshot from the in-process metrics store."""
    return metrics.snapshot()


@app.get("/api/search")
def search(q: str, limit: int = 10):
    """
    Semantic search over all processed files with stored embeddings.
    Embeds the query, computes cosine similarity against every stored vector,
    and returns the top `limit` results sorted by score descending.
    Files without embeddings (images, video, audio) are excluded from candidates.
    """
    query_vec = embed_text(q)
    rows = db.get_files_with_embeddings()

    results = []
    for row in rows:
        # Deserialise the JSON-encoded embedding stored in SQLite.
        try:
            file_vec = json.loads(row["embedding"]) if row.get("embedding") else []
        except Exception:
            file_vec = []
        score = cosine_similarity(query_vec, file_vec)
        results.append({**row, "score": score})

    # Return highest-scoring files first.
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Accepts a WebSocket connection and streams file-processed events in real time.
    Polls the shared event_queue every 200 ms and broadcasts each event as JSON
    to all connected clients. Removes the connection cleanly on disconnect.
    """
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            # Drain all available events and broadcast them.
            try:
                event = event_queue.get_nowait()
                for conn in active_connections:
                    try:
                        await conn.send_json(event)
                    except Exception:
                        pass  # Stale connection — will be removed on its own disconnect.
            except Exception:
                pass  # Queue empty — nothing to send this tick.
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
