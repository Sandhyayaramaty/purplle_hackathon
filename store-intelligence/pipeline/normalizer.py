"""
Event Normalizer
Reads raw JSONL events + POS CSV and outputs a unified event stream.
Reconciles ID schemes (ID_60001 vs track_id:101) and enriches with POS join.
"""

import json
import csv
import os
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional
import duckdb
from pathlib import Path
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

PROJECT_ROOT = BASE_DIR.parent.parent

RAW_EVENTS_PATH = PROJECT_ROOT / "events.jsonl"

POS_CSV_PATH = PROJECT_ROOT / "transactions.csv"

DB_PATH = PROJECT_ROOT / "data" / "store_intelligence.db"


# ── ID reconciliation ──────────────────────────────────────────────────────────
# Entry/exit events use "ID_60001" style; zone/queue events use track_id integers.
# We maintain a local map: track_id -> id_token built from the first entry event
# that logically precedes zone events (by timestamp proximity + store).

_id_map: dict[int, str] = {}   # track_id -> id_token
_token_attrs: dict[str, dict] = {}  # id_token -> {gender, age, age_bucket}


def _register_entry(event: dict):
    token = event.get("id_token")
    if token:
        _token_attrs[token] = {
            "gender": event.get("gender_pred"),
            "age":    event.get("age_pred"),
            "age_bucket": event.get("age_bucket"),
            "is_staff":   event.get("is_staff", False),
        }


def _resolve_visitor_id(event: dict) -> str:
    """Return a canonical visitor ID regardless of event type."""
    if "id_token" in event:
        return event["id_token"]
    track_id = event.get("track_id")
    if track_id and track_id in _id_map:
        return _id_map[track_id]
    # Fallback: synthesize from track_id
    return f"TRACK_{track_id}" if track_id else "UNKNOWN"


def _resolve_store_id(event: dict) -> str:
    raw = event.get("store_code") or event.get("store_id") or ""
    # Normalise "store_1076" -> "ST1076"
    if raw.startswith("store_"):
        return "ST" + raw.split("_")[1]
    return raw


def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    if not ts_str:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(ts_str, fmt)
        except ValueError:
            continue
    return None


# ── Normalise each raw event into unified schema ───────────────────────────────

def normalise_event(raw: dict) -> Optional[dict]:
    evt_type = raw.get("event_type")
    if not evt_type:
        return None

    store_id   = _resolve_store_id(raw)
    visitor_id = _resolve_visitor_id(raw)
    camera_id  = raw.get("camera_id") or raw.get("cam_id") or ""

    base = {
        "event_type": evt_type,
        "visitor_id": visitor_id,
        "store_id":   store_id,
        "camera_id":  camera_id,
        "gender":     raw.get("gender_pred") or raw.get("gender"),
        "age":        raw.get("age_pred")    or raw.get("age"),
        "age_bucket": raw.get("age_bucket"),
        "is_staff":   raw.get("is_staff", False),
        "group_id":   raw.get("group_id"),
        "group_size": raw.get("group_size"),
    }

    if evt_type in ("entry", "exit"):
        _register_entry(raw)
        base["timestamp"] = _parse_ts(raw.get("event_timestamp"))
        base["zone_id"]   = None
        base["zone_name"] = None
        base["zone_type"] = None
        base["dwell_seconds"] = None

    elif evt_type in ("zone_entered", "zone_exited"):
        base["timestamp"] = _parse_ts(raw.get("event_time"))
        base["zone_id"]   = raw.get("zone_id")
        base["zone_name"] = raw.get("zone_name")
        base["zone_type"] = raw.get("zone_type")
        base["is_revenue_zone"] = raw.get("is_revenue_zone") == "Yes"
        base["hotspot_x"] = raw.get("zone_hotspot_x")
        base["hotspot_y"] = raw.get("zone_hotspot_y")
        base["dwell_seconds"] = None

    elif evt_type in ("queue_completed", "queue_abandoned"):
        base["timestamp"]       = _parse_ts(raw.get("queue_join_ts"))
        base["zone_id"]         = raw.get("zone_id")
        base["zone_name"]       = raw.get("zone_name")
        base["zone_type"]       = "BILLING"
        base["wait_seconds"]    = raw.get("wait_seconds")
        base["abandoned"]       = raw.get("abandoned", False)
        base["queue_position"]  = raw.get("queue_position_at_join")
        base["queue_exit_ts"]   = _parse_ts(raw.get("queue_exit_ts"))
        base["dwell_seconds"]   = None

    else:
        return None  # Unknown event type

    return base


# ── Load POS transactions ──────────────────────────────────────────────────────

def load_pos(path: str) -> list[dict]:
    transactions = []
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                ts_str = f"{row['order_date']} {row['order_time']}"
                try:
                    ts = datetime.strptime(ts_str, "%d-%m-%Y %H:%M:%S")
                except ValueError:
                    ts = datetime.strptime(ts_str, "%m-%d-%Y %H:%M:%S")
                transactions.append({
                    "order_id":    row["order_id"],
                    "store_id":    row["store_id"],
                    "product_id":  row["product_id"],
                    "brand_name":  row["brand_name"],
                    "amount":      float(row["total_amount"]),
                    "timestamp":   ts,
                })
    except FileNotFoundError:
        print(f"[WARN] POS file not found: {path}")
    return transactions


# ── Zone-to-purchase attribution ───────────────────────────────────────────────
# For each completed queue event (= purchase), look back 30 min in zone events
# for the same visitor and tag which zones they browsed.

def attribute_zones_to_purchases(events: list[dict], transactions: list[dict]) -> list[dict]:
    """
    Enrich queue_completed events with zones browsed before checkout.
    Also enrich transactions with visitor_id if timestamps align.
    """
    # Index zone events by store
    zone_events = defaultdict(list)  # store_id -> [zone event]
    for e in events:
        if e["event_type"] in ("zone_entered", "zone_exited") and e["timestamp"]:
            zone_events[e["store_id"]].append(e)

    # Index queue completed events
    purchase_events = [e for e in events if e["event_type"] == "queue_completed"]

    # For each purchase, find which zones the visitor was in during last 30 min
    enriched = []
    for evt in events:
        if evt["event_type"] == "queue_completed" and evt["timestamp"]:
            lookback_start = evt["timestamp"] - timedelta(minutes=30)
            visitor = evt["visitor_id"]
            store   = evt["store_id"]
            browsed = [
                z["zone_name"] for z in zone_events[store]
                if z["visitor_id"] == visitor
                and z["event_type"] == "zone_entered"
                and z["timestamp"]
                and lookback_start <= z["timestamp"] <= evt["timestamp"]
            ]
            evt = {**evt, "zones_browsed_before_purchase": list(set(browsed))}
        enriched.append(evt)

    return enriched


# ── DuckDB persistence ─────────────────────────────────────────────────────────

def init_db(db_path: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    con.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_type      VARCHAR,
            visitor_id      VARCHAR,
            store_id        VARCHAR,
            camera_id       VARCHAR,
            timestamp       TIMESTAMP,
            gender          VARCHAR,
            age             INTEGER,
            age_bucket      VARCHAR,
            is_staff        BOOLEAN,
            group_id        VARCHAR,
            group_size      INTEGER,
            zone_id         VARCHAR,
            zone_name       VARCHAR,
            zone_type       VARCHAR,
            is_revenue_zone BOOLEAN,
            hotspot_x       DOUBLE,
            hotspot_y       DOUBLE,
            dwell_seconds   DOUBLE,
            wait_seconds    INTEGER,
            abandoned       BOOLEAN,
            queue_position  INTEGER,
            zones_browsed   VARCHAR
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            order_id   VARCHAR,
            store_id   VARCHAR,
            product_id VARCHAR,
            brand_name VARCHAR,
            amount     DOUBLE,
            timestamp  TIMESTAMP
        )
    """)
    return con


def insert_events(con: duckdb.DuckDBPyConnection, events: list[dict]):
    rows = []
    for e in events:
        rows.append((
            e.get("event_type"),
            e.get("visitor_id"),
            e.get("store_id"),
            e.get("camera_id"),
            e.get("timestamp"),
            e.get("gender"),
            e.get("age"),
            e.get("age_bucket"),
            e.get("is_staff", False),
            e.get("group_id"),
            e.get("group_size"),
            e.get("zone_id"),
            e.get("zone_name"),
            e.get("zone_type"),
            e.get("is_revenue_zone"),
            e.get("hotspot_x"),
            e.get("hotspot_y"),
            e.get("dwell_seconds"),
            e.get("wait_seconds"),
            e.get("abandoned", False),
            e.get("queue_position"),
            json.dumps(e.get("zones_browsed_before_purchase", [])),
        ))
    con.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)


def insert_transactions(con: duckdb.DuckDBPyConnection, transactions: list[dict]):
    rows = [(t["order_id"], t["store_id"], t["product_id"],
             t["brand_name"], t["amount"], t["timestamp"]) for t in transactions]
    if rows:
        con.executemany(
        "INSERT INTO transactions VALUES (?,?,?,?,?,?)",
        rows)
    else:
        print("No transactions found. Skipping transaction load.")


# ── Main ──────────────────────────────────────────────────────────────────────

def run_pipeline(events_path=RAW_EVENTS_PATH, pos_path=POS_CSV_PATH, db_path=DB_PATH):
    print("[1/4] Reading raw JSONL events...")
    raw_events = []
    with open(events_path) as f:
        for line in f:
            line = line.strip()
            if line:
                raw_events.append(json.loads(line))

    print(f"      {len(raw_events)} raw events loaded")

    print("[2/4] Normalising events...")
    normalised = [e for e in (normalise_event(r) for r in raw_events) if e]
    print(f"      {len(normalised)} normalised events")

    print("[3/4] Loading POS transactions...")
    transactions = load_pos(pos_path)
    print(f"      {len(transactions)} transactions loaded")

    print("[4/4] Attributing zones to purchases & writing to DB...")
    enriched = attribute_zones_to_purchases(normalised, transactions)
    con = init_db(db_path)
    con.execute("DELETE FROM events")
    con.execute("DELETE FROM transactions")
    insert_events(con, enriched)
    insert_transactions(con, transactions)
    con.close()
    print(f"      Done. DB at: {db_path}")
    return enriched, transactions


if __name__ == "__main__":
    run_pipeline()
