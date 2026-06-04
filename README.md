# Store Intelligence System

AI-powered retail analytics pipeline — CCTV + POS → real-time KPIs, zone heatmaps, anomaly detection, and a production REST API.

---

## Architecture

```
Raw Inputs          CV Pipeline           Event Stream          Analytics             API + Dashboard
──────────          ───────────           ────────────          ─────────             ───────────────
CCTV Videos    →   YOLOv8 detect    →    Event normalizer  →   DuckDB queries   →   FastAPI REST
Store layouts  →   ByteTrack track  →    POS enrichment    →   Zone attribution →   WebSocket feed
Events JSONL   →   Zone mapping     →    Unified schema    →   Anomaly detect   →   Streamlit UI
POS CSV        ─────────────────────────────────────────────────────────────────→   /alerts webhook
```

**Key design decision — schema-first**: The JSONL event schema was defined before the CV model was built, so the vision pipeline is just a *producer into a contract*. This mirrors real production practice.

---

## Quick Start (< 5 minutes)

### Option A — Docker (recommended)

```bash
# 1. Clone and add your data files
cp your_events.jsonl data/sample_events.jsonl
cp your_pos.csv      data/POS_sample_transactions.csv

# 2. Start everything
docker compose up --build

# API  → http://localhost:8000/docs
# Dash → http://localhost:8501
```

### Option B — Local Python

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run the normalizer (builds DuckDB from your files)
python pipeline/normalizer.py

# Start the API
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# In another terminal, start the dashboard
streamlit run dashboard/app.py
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System health check |
| GET | `/stores` | List all store IDs |
| GET | `/store/{id}/metrics` | Footfall KPIs + hourly breakdown |
| GET | `/store/{id}/zones/heatmap` | Per-zone visit counts + coordinates |
| GET | `/store/{id}/zones/conversion` | Zone → purchase attribution |
| GET | `/store/{id}/queue` | Queue wait times (P50/P90), abandon rate |
| GET | `/store/{id}/revenue` | Revenue summary + by-hour |
| GET | `/store/{id}/brands` | Top brands by revenue |
| GET | `/alerts?store_id=&severity=` | Anomaly alerts (high/medium/low) |
| GET | `/store/{id}/report` | Full composite report (all above) |
| WS | `/ws/live/{store_id}` | Live occupancy WebSocket stream |
| POST | `/ingest/event` | Real-time event ingestion |

Interactive docs: `http://localhost:8000/docs`

---

## CV Pipeline

Run on a video file:
```bash
python pipeline/cv_pipeline.py \
  --video   data/store_1076_cam1.mp4 \
  --layout  data/layouts/store_1076.json \
  --store   ST1076 \
  --camera  CAM1 \
  --output  data/cv_events.jsonl \
  --sample  5        # process every 5th frame
```

The pipeline outputs JSONL in the same unified schema as the API, so you can feed it straight into `/ingest/event` or re-run the normalizer.

**Models used:**
- Detection: `yolov8n.pt` (person class only) — swap to `yolov8m.pt` for higher accuracy
- Tracking: IoU-based tracker (drop-in replace with ByteTrack via `supervision` library)
- Attributes: Mock predictor — replace `predict_attributes()` in `cv_pipeline.py` with InsightFace or a fine-tuned MobileNetV3

---

## Store Layout Format

`data/layouts/store_1076.json`:
```json
{
  "store_id": "ST1076",
  "cameras": {
    "CAM1": { "role": "entrance", "fov_polygon": [[0,0],[1,0],[1,1],[0,1]] }
  },
  "zones": [
    {
      "zone_id": "Z01",
      "zone_name": "Left Shelf",
      "zone_type": "SHELF",
      "is_revenue_zone": true,
      "polygon": [[0.05,0.1],[0.30,0.1],[0.30,0.85],[0.05,0.85]]
    }
  ]
}
```
Polygon coordinates are normalised 0–1 relative to the camera frame.

---

## Event Schema (Unified)

Every event in DuckDB has this structure:

| Field | Type | Description |
|-------|------|-------------|
| `event_type` | str | entry / exit / zone_entered / zone_exited / queue_completed / queue_abandoned |
| `visitor_id` | str | Canonical visitor token |
| `store_id` | str | Normalised store ID (e.g. ST1076) |
| `camera_id` | str | Camera that detected the event |
| `timestamp` | datetime | Event time |
| `gender` | str | M / F (predicted) |
| `age` | int | Predicted age |
| `age_bucket` | str | 25-34, 35-44, etc. |
| `zone_id` | str | Zone identifier |
| `zone_name` | str | Human-readable zone name |
| `zone_type` | str | SHELF / DISPLAY / BILLING / FOYER |
| `wait_seconds` | int | Queue wait time (billing events only) |
| `abandoned` | bool | True if queue abandoned |
| `zones_browsed` | JSON | Zones visited before purchase (queue events) |

---

## Key Analytics

### Zone → Purchase Attribution
The most differentiating insight: for each completed purchase (`queue_completed`), the pipeline looks back 30 minutes and joins all `zone_entered` events for the same visitor. This tells you *which zones drove purchases* — not just which zones had traffic.

### Anomaly Detection (Rule-based)
| Type | Trigger | Severity |
|------|---------|---------|
| `long_queue_wait` | Wait > 120s | High (>180s) / Medium |
| `queue_abandoned` | Any abandon | Medium |
| `no_zone_engagement` | Entry with no zone events | Low (shrinkage signal) |

---

## Project Structure

```
store-intelligence/
├── api/
│   ├── main.py          # FastAPI server + WebSocket
│   └── analytics.py     # All SQL analytics queries
├── pipeline/
│   ├── normalizer.py    # JSONL + CSV → unified DuckDB schema
│   └── cv_pipeline.py   # YOLOv8 + tracker + zone mapper
├── dashboard/
│   └── app.py           # Streamlit dashboard
├── data/
│   ├── layouts/
│   │   └── store_1076.json
│   ├── sample_events.jsonl
│   └── POS_sample_transactions.csv
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## Trade-offs & Decisions

| Decision | Choice | Alternative | Why |
|----------|--------|------------|-----|
| Storage | DuckDB | PostgreSQL + TimescaleDB | Zero-ops, embedded, fast analytical SQL |
| Detection | YOLOv8n | Detectron2 | Faster inference, easy deployment |
| Tracking | IoU-based | DeepSORT / ByteTrack | Simpler dependency; swap in `supervision` for production |
| API | FastAPI | Flask / Django | Native async, WebSocket, auto-docs |
| Dashboard | Streamlit | Grafana | Faster to build; Grafana recommended for prod |
| Streaming | In-process | Kafka / Redis Streams | Right size for challenge; add Kafka for multi-store prod |
