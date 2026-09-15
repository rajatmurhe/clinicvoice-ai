import sqlite3
import time
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'dashboard.db')


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
            latency_ms REAL
        )
    ''')
    conn.commit()
    conn.close()


def log_query(query, response, intent, agent, guardrail_triggered, cache_hit, latency_ms):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO query_log (timestamp, query, response, intent, agent, guardrail_triggered, cache_hit, latency_ms) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (time.time(), query, response, intent, agent, int(guardrail_triggered), int(cache_hit), latency_ms)
    )
    conn.commit()
    conn.close()


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

    avg_latency = conn.execute(
        'SELECT AVG(latency_ms) as avg FROM query_log WHERE latency_ms IS NOT NULL'
    ).fetchone()['avg']

    recent = conn.execute(
        'SELECT * FROM query_log ORDER BY timestamp DESC LIMIT 20'
    ).fetchall()

    conn.close()

    return {
        'total_queries': total,
        'by_agent': {row['agent']: row['count'] for row in by_agent},
        'guardrail_triggered_count': guardrail_count,
        'cache_hit_rate': round(cache_hits / faq_total, 3) if faq_total > 0 else 0,
        'avg_latency_ms': round(avg_latency, 1) if avg_latency else None,
        'recent_queries': [dict(row) for row in recent]
    }


init_db()
