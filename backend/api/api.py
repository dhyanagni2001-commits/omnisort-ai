import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from backend.database import db
from backend.watcher.file_watcher import event_queue
from backend.metrics.metrics import metrics

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
