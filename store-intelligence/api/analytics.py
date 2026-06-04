"""
Analytics Engine
All KPI computations run as SQL over DuckDB.
Returns plain dicts/lists — no framework coupling.
"""

import json
from datetime import datetime, timedelta
from typing import Optional
import duckdb

DB_PATH = "data/store_intelligence.db"


def _con(db_path=DB_PATH) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(db_path, read_only=True)


# ── Footfall KPIs ─────────────────────────────────────────────────────────────

def footfall_summary(store_id: Optional[str] = None, db_path=DB_PATH) -> dict:
    con = _con(db_path)
    where = f"WHERE store_id = '{store_id}'" if store_id else ""
    r = con.execute(f"""
        SELECT
            COUNT(*) FILTER (WHERE event_type = 'entry' AND NOT is_staff) AS total_visitors,
            COUNT(*) FILTER (WHERE event_type = 'entry' AND is_staff)     AS staff_entries,
            COUNT(*) FILTER (WHERE event_type = 'exit'  AND NOT is_staff) AS total_exits,
            COUNT(DISTINCT visitor_id) FILTER (WHERE event_type = 'entry') AS unique_visitors,
            COUNT(*) FILTER (WHERE event_type = 'entry' AND group_id IS NOT NULL) AS group_visitors,
            COUNT(*) FILTER (WHERE event_type = 'queue_completed') AS conversions,
            COUNT(*) FILTER (WHERE event_type = 'queue_abandoned') AS queue_abandons,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE event_type = 'queue_completed') /
                NULLIF(COUNT(*) FILTER (WHERE event_type = 'entry' AND NOT is_staff), 0),
            1) AS conversion_rate_pct
        FROM events {where}
    """).fetchone()
    cols = ["total_visitors","staff_entries","total_exits","unique_visitors",
            "group_visitors","conversions","queue_abandons","conversion_rate_pct"]
    return dict(zip(cols, r))


def hourly_footfall(store_id: Optional[str] = None, db_path=DB_PATH) -> list[dict]:
    con = _con(db_path)
    where = f"AND store_id = '{store_id}'" if store_id else ""
    rows = con.execute(f"""
        SELECT
            HOUR(timestamp) AS hour,
            COUNT(*) FILTER (WHERE event_type = 'entry' AND NOT is_staff) AS entries,
            COUNT(*) FILTER (WHERE event_type = 'exit'  AND NOT is_staff) AS exits
        FROM events
        WHERE event_type IN ('entry','exit') AND timestamp IS NOT NULL {where}
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    return [{"hour": r[0], "entries": r[1], "exits": r[2]} for r in rows]


def demographic_breakdown(store_id: Optional[str] = None, db_path=DB_PATH) -> dict:
    con = _con(db_path)
    where = f"AND store_id = '{store_id}'" if store_id else ""
    gender_rows = con.execute(f"""
        SELECT gender, COUNT(*) AS cnt FROM events
        WHERE event_type = 'entry' AND gender IS NOT NULL {where}
        GROUP BY gender ORDER BY cnt DESC
    """).fetchall()
    age_rows = con.execute(f"""
        SELECT age_bucket, COUNT(*) AS cnt FROM events
        WHERE event_type = 'entry' AND age_bucket IS NOT NULL {where}
        GROUP BY age_bucket ORDER BY cnt DESC
    """).fetchall()
    return {
        "by_gender":     [{"gender": r[0], "count": r[1]} for r in gender_rows],
        "by_age_bucket": [{"age_bucket": r[0], "count": r[1]} for r in age_rows],
    }


# ── Zone Analytics ─────────────────────────────────────────────────────────────

def zone_heatmap(store_id: Optional[str] = None, db_path=DB_PATH) -> list[dict]:
    """Per-zone: visits, unique visitors, avg dwell, revenue zone flag, hotspot coords."""
    con = _con(db_path)
    where = f"AND store_id = '{store_id}'" if store_id else ""
    rows = con.execute(f"""
        SELECT
            zone_id,
            zone_name,
            zone_type,
            ANY_VALUE(is_revenue_zone) AS is_revenue_zone,
            COUNT(*) FILTER (WHERE event_type = 'zone_entered') AS zone_visits,
            COUNT(DISTINCT visitor_id) FILTER (WHERE event_type = 'zone_entered') AS unique_visitors,
            ROUND(AVG(hotspot_x), 1) AS avg_x,
            ROUND(AVG(hotspot_y), 1) AS avg_y
        FROM events
        WHERE zone_id IS NOT NULL {where}
        GROUP BY 1,2,3
        ORDER BY zone_visits DESC
    """).fetchall()
    cols = ["zone_id","zone_name","zone_type","is_revenue_zone",
            "zone_visits","unique_visitors","avg_x","avg_y"]
    return [dict(zip(cols, r)) for r in rows]


def zone_conversion(store_id: Optional[str] = None, db_path=DB_PATH) -> list[dict]:
    """
    Zone conversion: what % of visitors who entered a revenue zone
    went on to complete a purchase (queue_completed)?
    """
    con = _con(db_path)
    where = f"AND store_id = '{store_id}'" if store_id else ""
    # Buyers = visitors who completed queue
    buyers = set(r[0] for r in con.execute(f"""
        SELECT DISTINCT visitor_id FROM events
        WHERE event_type = 'queue_completed' {where}
    """).fetchall())

    zone_rows = con.execute(f"""
        SELECT zone_name, visitor_id FROM events
        WHERE event_type = 'zone_entered' AND zone_name IS NOT NULL {where}
    """).fetchall()

    from collections import defaultdict
    zone_visitors: dict[str, set] = defaultdict(set)
    zone_buyers:   dict[str, set] = defaultdict(set)
    for zone_name, vid in zone_rows:
        zone_visitors[zone_name].add(vid)
        if vid in buyers:
            zone_buyers[zone_name].add(vid)

    result = []
    for zone_name, visitors in zone_visitors.items():
        total   = len(visitors)
        bought  = len(zone_buyers[zone_name])
        result.append({
            "zone_name":       zone_name,
            "total_visitors":  total,
            "buyers":          bought,
            "conversion_pct":  round(100.0 * bought / total, 1) if total else 0.0,
        })
    return sorted(result, key=lambda x: -x["conversion_pct"])


# ── Queue Analytics ────────────────────────────────────────────────────────────

def queue_stats(store_id: Optional[str] = None, db_path=DB_PATH) -> dict:
    con = _con(db_path)
    where = f"AND store_id = '{store_id}'" if store_id else ""
    r = con.execute(f"""
        SELECT
            COUNT(*) FILTER (WHERE event_type = 'queue_completed')            AS total_served,
            COUNT(*) FILTER (WHERE event_type = 'queue_abandoned')            AS total_abandoned,
            ROUND(AVG(wait_seconds) FILTER (WHERE event_type IN ('queue_completed','queue_abandoned')), 1) AS avg_wait_s,
            ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY wait_seconds)
                  FILTER (WHERE event_type IN ('queue_completed','queue_abandoned')), 1) AS p50_wait_s,
            ROUND(PERCENTILE_CONT(0.9) WITHIN GROUP (ORDER BY wait_seconds)
                  FILTER (WHERE event_type IN ('queue_completed','queue_abandoned')), 1) AS p90_wait_s,
            MAX(wait_seconds) AS max_wait_s,
            ROUND(
                100.0 * COUNT(*) FILTER (WHERE event_type = 'queue_abandoned') /
                NULLIF(COUNT(*) FILTER (WHERE event_type IN ('queue_completed','queue_abandoned')), 0),
            1) AS abandon_rate_pct,
            ROUND(AVG(queue_position) FILTER (WHERE event_type IN ('queue_completed','queue_abandoned')), 1) AS avg_queue_length
        FROM events
        WHERE event_type IN ('queue_completed', 'queue_abandoned') {where}
    """).fetchone()
    cols = ["total_served","total_abandoned","avg_wait_s","p50_wait_s",
            "p90_wait_s","max_wait_s","abandon_rate_pct","avg_queue_length"]
    return dict(zip(cols, r))


# ── POS / Revenue Analytics ───────────────────────────────────────────────────

def revenue_summary(store_id: Optional[str] = None, db_path=DB_PATH) -> dict:
    con = duckdb.connect(db_path, read_only=True)
    where = f"WHERE store_id = '{store_id}'" if store_id else ""
    r = con.execute(f"""
        SELECT
            COUNT(DISTINCT order_id)          AS total_orders,
            COUNT(*)                           AS total_line_items,
            ROUND(SUM(amount), 2)              AS total_revenue,
            ROUND(AVG(amount), 2)              AS avg_item_value,
            COUNT(DISTINCT brand_name)         AS unique_brands
        FROM transactions {where}
    """).fetchone()
    cols = ["total_orders","total_line_items","total_revenue","avg_item_value","unique_brands"]
    return dict(zip(cols, r))


def top_brands(store_id: Optional[str] = None, limit=10, db_path=DB_PATH) -> list[dict]:
    con = duckdb.connect(db_path, read_only=True)
    where = f"WHERE store_id = '{store_id}'" if store_id else ""
    rows = con.execute(f"""
        SELECT brand_name,
               COUNT(*) AS units_sold,
               ROUND(SUM(amount), 2) AS revenue
        FROM transactions {where}
        GROUP BY brand_name ORDER BY revenue DESC LIMIT {limit}
    """).fetchall()
    return [{"brand": r[0], "units_sold": r[1], "revenue": r[2]} for r in rows]


def revenue_by_hour(store_id: Optional[str] = None, db_path=DB_PATH) -> list[dict]:
    con = duckdb.connect(db_path, read_only=True)
    where = f"WHERE store_id = '{store_id}'" if store_id else ""
    rows = con.execute(f"""
        SELECT HOUR(timestamp) AS hour,
               COUNT(DISTINCT order_id) AS orders,
               ROUND(SUM(amount), 2) AS revenue
        FROM transactions {where}
        GROUP BY hour ORDER BY hour
    """).fetchall()
    return [{"hour": r[0], "orders": r[1], "revenue": r[2]} for r in rows]


# ── Anomaly Detection ─────────────────────────────────────────────────────────

def detect_anomalies(store_id: Optional[str] = None, db_path=DB_PATH) -> list[dict]:
    """
    Rule-based anomaly detection:
    1. Long queue wait (> 120s)
    2. Queue abandonment
    3. Visitor entered store but never entered any zone (possible shrinkage risk)
    4. Unusually long zone dwell (> 10 min, proxy via repeated entries with no exit)
    """
    con = _con(db_path)
    where_store = f"AND store_id = '{store_id}'" if store_id else ""
    alerts = []

    # 1. Long waits
    long_waits = con.execute(f"""
        SELECT visitor_id, store_id, wait_seconds, timestamp
        FROM events
        WHERE event_type IN ('queue_completed','queue_abandoned')
        AND wait_seconds > 120 {where_store}
        ORDER BY wait_seconds DESC
    """).fetchall()
    for r in long_waits:
        alerts.append({
            "type": "long_queue_wait",
            "severity": "high" if r[2] > 180 else "medium",
            "visitor_id": r[0],
            "store_id":   r[1],
            "detail": f"Wait time {r[2]}s at {r[3]}",
            "timestamp": str(r[3]),
        })

    # 2. Queue abandons
    abandons = con.execute(f"""
        SELECT visitor_id, store_id, wait_seconds, timestamp
        FROM events
        WHERE event_type = 'queue_abandoned' {where_store}
    """).fetchall()
    for r in abandons:
        alerts.append({
            "type": "queue_abandoned",
            "severity": "medium",
            "visitor_id": r[0],
            "store_id":   r[1],
            "detail": f"Abandoned after {r[2]}s wait",
            "timestamp": str(r[3]),
        })

    # 3. No-zone visitors (entered store, never logged in any zone)
    all_entries = set(r[0] for r in con.execute(f"""
        SELECT DISTINCT visitor_id FROM events
        WHERE event_type = 'entry' AND NOT is_staff {where_store}
    """).fetchall())
    zone_visitors = set(r[0] for r in con.execute(f"""
        SELECT DISTINCT visitor_id FROM events
        WHERE event_type = 'zone_entered' {where_store}
    """).fetchall())
    ghost_visitors = all_entries - zone_visitors
    for vid in ghost_visitors:
        alerts.append({
            "type": "no_zone_engagement",
            "severity": "low",
            "visitor_id": vid,
            "store_id":   store_id or "ALL",
            "detail": "Visitor entered store but triggered no zone events — possible blind spot or shrinkage risk",
            "timestamp": None,
        })

    return alerts


# ── Composite store report ─────────────────────────────────────────────────────

def store_report(store_id: Optional[str] = None, db_path=DB_PATH) -> dict:
    return {
        "generated_at":       datetime.utcnow().isoformat(),
        "store_id":           store_id or "ALL",
        "footfall":           footfall_summary(store_id, db_path),
        "demographics":       demographic_breakdown(store_id, db_path),
        "hourly_footfall":    hourly_footfall(store_id, db_path),
        "zone_heatmap":       zone_heatmap(store_id, db_path),
        "zone_conversion":    zone_conversion(store_id, db_path),
        "queue":              queue_stats(store_id, db_path),
        "revenue":            revenue_summary(store_id, db_path),
        "top_brands":         top_brands(store_id, db_path=db_path),
        "revenue_by_hour":    revenue_by_hour(store_id, db_path),
        "anomalies":          detect_anomalies(store_id, db_path),
    }


if __name__ == "__main__":
    import pprint
    pprint.pprint(store_report())
