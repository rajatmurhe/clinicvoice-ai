import json
import os
import sqlite3
import time

_DATA_DIR = os.environ.get("CLINICVOICE_DATA_DIR") or os.path.dirname(__file__)
DB_PATH = os.path.join(_DATA_DIR, 'dashboard.db')

# Rough cost estimate for the dashboard card. Tokens are real (from the LLM
# response); the rate is an estimate and configurable.
COST_PER_MTOKEN = float(os.environ.get("CLINICVOICE_COST_PER_MTOKEN", "0.07"))


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp REAL,
            query TEXT,
            response TEXT,
            intent TEXT,
            agent TEXT,
            guardrail_triggered INTEGER,
            cache_hit INTEGER,
            latency_ms REAL,
            request_id TEXT,
            error_type TEXT,
            tokens INTEGER
        )
    ''')
    conn.commit()
    _migrate(conn)
    conn.close()


def _migrate(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(query_log)")]
    if "request_id" not in cols:
        conn.execute("ALTER TABLE query_log ADD COLUMN request_id TEXT")
    if "error_type" not in cols:
        conn.execute("ALTER TABLE query_log ADD COLUMN error_type TEXT")
    if "tokens" not in cols:
        conn.execute("ALTER TABLE query_log ADD COLUMN tokens INTEGER")
    conn.commit()


def log_query(query, response, intent, agent, guardrail_triggered, cache_hit, latency_ms,
              request_id=None, error_type=None, tokens=None):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO query_log (timestamp, query, response, intent, agent, guardrail_triggered, cache_hit, latency_ms, request_id, error_type, tokens) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
        (time.time(), query, response, intent, agent, int(guardrail_triggered), int(cache_hit), latency_ms, request_id, error_type, tokens)
    )
    conn.commit()
    conn.close()


def _percentile(sorted_values, p):
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * (p / 100.0)
    f = int(k)
    c = min(f + 1, len(sorted_values) - 1)
    if f == c:
        return sorted_values[f]
    return sorted_values[f] + (sorted_values[c] - sorted_values[f]) * (k - f)


def get_stats():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    total = conn.execute('SELECT COUNT(*) as c FROM query_log').fetchone()['c']

    by_agent = conn.execute(
        'SELECT agent, COUNT(*) as count FROM query_log GROUP BY agent'
    ).fetchall()

    guardrail_count = conn.execute(
        'SELECT COUNT(*) as c FROM query_log WHERE guardrail_triggered = 1'
    ).fetchone()['c']

    cache_hits = conn.execute(
        'SELECT COUNT(*) as c FROM query_log WHERE cache_hit = 1'
    ).fetchone()['c']

    faq_total = conn.execute(
        "SELECT COUNT(*) as c FROM query_log WHERE agent = 'faq'"
    ).fetchone()['c']

    latencies = [r['latency_ms'] for r in conn.execute(
        'SELECT latency_ms FROM query_log WHERE latency_ms IS NOT NULL ORDER BY latency_ms'
    )]

    failures = conn.execute(
        'SELECT COUNT(*) as c FROM query_log WHERE error_type IS NOT NULL'
    ).fetchone()['c']

    tokens_total = conn.execute(
        'SELECT SUM(tokens) as t FROM query_log WHERE tokens IS NOT NULL'
    ).fetchone()['t'] or 0

    recent = conn.execute(
        'SELECT * FROM query_log ORDER BY timestamp DESC LIMIT 20'
    ).fetchall()

    conn.close()

    return {
        'total_queries': total,
        'by_agent': {row['agent']: row['count'] for row in by_agent},
        'guardrail_triggered_count': guardrail_count,
        'cache_hit_rate': round(cache_hits / faq_total, 3) if faq_total > 0 else 0,
        'avg_latency_ms': round(sum(latencies) / len(latencies), 1) if latencies else None,
        'p50_latency_ms': round(_percentile(latencies, 50), 1) if latencies else None,
        'p95_latency_ms': round(_percentile(latencies, 95), 1) if latencies else None,
        'failure_count': failures,
        'tokens_total': tokens_total,
        'estimated_cost_usd': round(tokens_total / 1_000_000 * COST_PER_MTOKEN, 4),
        'recent_queries': [dict(row) for row in recent]
    }


def get_recent_failures(limit=20):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        'SELECT * FROM query_log WHERE error_type IS NOT NULL ORDER BY timestamp DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


init_db()
