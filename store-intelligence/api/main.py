"""
Store Intelligence API
FastAPI server exposing REST endpoints + WebSocket live feed.

Endpoints:
  GET  /health
  GET  /stores
  GET  /store/{store_id}/metrics
  GET  /store/{store_id}/zones/heatmap
  GET  /store/{store_id}/zones/conversion
  GET  /store/{store_id}/queue
  GET  /store/{store_id}/revenue
  GET  /store/{store_id}/brands
  GET  /alerts?store_id=&severity=
  GET  /store/{store_id}/report          (full composite)
  WS   /ws/live/{store_id}               (live occupancy stream)
  POST /ingest/event                     (single event ingestion)
"""

import asyncio
import json
import os
import random
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from api.analytics import (
    footfall_summary, hourly_footfall, demographic_breakdown,
    zone_heatmap, zone_conversion, queue_stats,
    revenue_summary, top_brands, revenue_by_hour,
    detect_anomalies, store_report,
)
from pipeline.normalizer import normalise_event, init_db, insert_events

DB_PATH = os.environ.get("DB_PATH", "data/store_intelligence.db")

app = FastAPI(
    title="Store Intelligence System",
    description="AI-powered retail analytics API from CCTV + POS data",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── In-memory live occupancy state (updated by /ingest/event) ─────────────────
_live_occupancy: dict[str, int] = {}   # store_id -> current count
_ws_clients: dict[str, list[WebSocket]] = {}  # store_id -> [ws]


# ── Health ────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


# ── Store list ────────────────────────────────────────────────────────────────

@app.get("/stores", tags=["Stores"])
def list_stores():
    import duckdb
    con = duckdb.connect(DB_PATH, read_only=True)
    rows = con.execute("SELECT DISTINCT store_id FROM events ORDER BY store_id").fetchall()
    return {"stores": [r[0] for r in rows]}


# ── Footfall ──────────────────────────────────────────────────────────────────

@app.get("/store/{store_id}/metrics", tags=["Footfall"])
def get_metrics(store_id: str):
    try:
        return {
            "store_id": store_id,
            "footfall": footfall_summary(store_id, DB_PATH),
            "demographics": demographic_breakdown(store_id, DB_PATH),
            "hourly": hourly_footfall(store_id, DB_PATH),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Zone analytics ────────────────────────────────────────────────────────────

@app.get("/store/{store_id}/zones/heatmap", tags=["Zones"])
def get_zone_heatmap(store_id: str):
    return {"store_id": store_id, "zones": zone_heatmap(store_id, DB_PATH)}


@app.get("/store/{store_id}/zones/conversion", tags=["Zones"])
def get_zone_conversion(store_id: str):
    return {"store_id": store_id, "conversion": zone_conversion(store_id, DB_PATH)}


# ── Queue ─────────────────────────────────────────────────────────────────────

@app.get("/store/{store_id}/queue", tags=["Queue"])
def get_queue(store_id: str):
    return {"store_id": store_id, "queue": queue_stats(store_id, DB_PATH)}


# ── Revenue / POS ─────────────────────────────────────────────────────────────

@app.get("/store/{store_id}/revenue", tags=["Revenue"])
def get_revenue(store_id: str):
    return {
        "store_id": store_id,
        "summary": revenue_summary(store_id, DB_PATH),
        "by_hour": revenue_by_hour(store_id, DB_PATH),
    }


@app.get("/store/{store_id}/brands", tags=["Revenue"])
def get_brands(store_id: str, limit: int = Query(10, ge=1, le=50)):
    return {"store_id": store_id, "brands": top_brands(store_id, limit, DB_PATH)}


# ── Alerts / Anomalies ────────────────────────────────────────────────────────

@app.get("/alerts", tags=["Anomalies"])
def get_alerts(
    store_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, regex="^(high|medium|low)$"),
):
    alerts = detect_anomalies(store_id, DB_PATH)
    if severity:
        alerts = [a for a in alerts if a["severity"] == severity]
    return {
        "count": len(alerts),
        "alerts": sorted(alerts, key=lambda a: {"high": 0, "medium": 1, "low": 2}[a["severity"]]),
    }


# ── Full report ───────────────────────────────────────────────────────────────

@app.get("/store/{store_id}/report", tags=["Reports"])
def get_full_report(store_id: str):
    try:
        return store_report(store_id, DB_PATH)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Event ingestion ───────────────────────────────────────────────────────────

class RawEvent(BaseModel):
    model_config = {"extra": "allow"}  # accept any extra fields

@app.post("/ingest/event", tags=["Ingestion"])
async def ingest_event(raw: RawEvent):
    """
    Accepts a raw CV event (same schema as the JSONL file),
    normalises it, persists it, and pushes a live update to WebSocket subscribers.
    """
    event_dict = raw.model_dump()
    normalised = normalise_event(event_dict)
    if not normalised:
        raise HTTPException(status_code=422, detail="Could not normalise event")

    # Persist
    con = init_db(DB_PATH)
    insert_events(con, [normalised])
    con.close()

    # Update live occupancy
    store = normalised["store_id"]
    if normalised["event_type"] == "entry":
        _live_occupancy[store] = _live_occupancy.get(store, 0) + 1
    elif normalised["event_type"] == "exit":
        _live_occupancy[store] = max(0, _live_occupancy.get(store, 0) - 1)

    # Broadcast to WebSocket clients
    payload = json.dumps({
        "store_id":  store,
        "occupancy": _live_occupancy.get(store, 0),
        "event":     normalised["event_type"],
        "ts":        datetime.utcnow().isoformat(),
    })
    for ws in _ws_clients.get(store, []):
        try:
            await ws.send_text(payload)
        except Exception:
            pass

    return {"status": "ok", "event_type": normalised["event_type"], "store_id": store}


# ── WebSocket live feed ───────────────────────────────────────────────────────

@app.websocket("/ws/live/{store_id}")
async def ws_live(websocket: WebSocket, store_id: str):
    """
    Streams live occupancy updates for a store.
    Sends a heartbeat every 5s with current occupancy.
    """
    await websocket.accept()
    if store_id not in _ws_clients:
        _ws_clients[store_id] = []
    _ws_clients[store_id].append(websocket)

    try:
        while True:
            # Heartbeat
            await websocket.send_text(json.dumps({
                "store_id":  store_id,
                "occupancy": _live_occupancy.get(store_id, 0),
                "type":      "heartbeat",
                "ts":        datetime.utcnow().isoformat(),
            }))
            await asyncio.sleep(5)
    except WebSocketDisconnect:
        _ws_clients[store_id].remove(websocket)


# ── Startup: run pipeline if DB is empty ─────────────────────────────────────

@app.on_event("startup")
async def startup():
    import duckdb, os
    os.makedirs("data", exist_ok=True)
    try:
        con = duckdb.connect(DB_PATH, read_only=True)
        count = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        con.close()
        if count == 0:
            raise ValueError("empty")
    except Exception:
        print("[startup] DB empty or missing — running pipeline...")
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
        from pipeline.normalizer import run_pipeline
        run_pipeline()
        print("[startup] Pipeline complete.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)
