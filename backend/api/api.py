import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.database import db
from backend.watcher.file_watcher import event_queue
from backend.metrics.metrics import metrics
from backend.embeddings.embedding import embed_text, cosine_similarity

app = FastAPI(title="OmniSort AI", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections: list[WebSocket] = []

@app.on_event("startup")
def on_startup():
    db.init_db()

@app.get("/api/health")
def health():
    return {"status": "ok"}

@app.get("/api/stats")
def stats():
    return db.get_stats()

@app.get("/api/files")
def files(limit: int = 50, offset: int = 0):
    return db.get_files(limit=limit, offset=offset)

@app.get("/api/metrics")
def get_metrics():
    return metrics.snapshot()

@app.get("/api/search")
def search(q: str, limit: int = 10):
    """Semantic search over processed files using cosine similarity."""
    query_vec = embed_text(q)
    rows = db.get_files_with_embeddings()
    results = []
    for row in rows:
        try:
            file_vec = json.loads(row["embedding"]) if row.get("embedding") else []
        except Exception:
            file_vec = []
        score = cosine_similarity(query_vec, file_vec)
        results.append({**row, "score": score})
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    try:
        while True:
            try:
                event = event_queue.get_nowait()
                for conn in active_connections:
                    try:
                        await conn.send_json(event)
                    except Exception:
                        pass
            except Exception:
                pass
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
