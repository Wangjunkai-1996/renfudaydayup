import os
import sqlite3


def _normalize_code(code):
    return str(code or '').strip().lower()


def _connect(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_watchlist_table(conn):
    conn.execute(
        '''
        CREATE TABLE IF NOT EXISTS watchlist (
            code TEXT PRIMARY KEY,
            name TEXT DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        '''
    )


def upsert_entry(db_path, code, name=''):
    normalized = _normalize_code(code)
    if not normalized:
        return
    conn = _connect(db_path)
    try:
        ensure_watchlist_table(conn)
        row = conn.execute(
            'SELECT sort_order FROM watchlist WHERE code=?',
            (normalized,)
        ).fetchone()
        if row:
            conn.execute(
                'UPDATE watchlist SET name=?, enabled=1, updated_at=CURRENT_TIMESTAMP WHERE code=?',
                (str(name or ''), normalized)
            )
        else:
            next_order = conn.execute(
                'SELECT COALESCE(MAX(sort_order), 0) + 1 AS next_order FROM watchlist'
            ).fetchone()['next_order']
            conn.execute(
                '''
                INSERT INTO watchlist (code, name, enabled, sort_order)
                VALUES (?,?,1,?)
                ''',
                (normalized, str(name or ''), int(next_order or 1))
            )
        conn.commit()
    finally:
        conn.close()


def remove_entry(db_path, code):
    normalized = _normalize_code(code)
    if not normalized:
        return
    conn = _connect(db_path)
    try:
        ensure_watchlist_table(conn)
        conn.execute('DELETE FROM watchlist WHERE code=?', (normalized,))
        conn.commit()
    finally:
        conn.close()


def list_enabled_codes(db_path):
    conn = _connect(db_path)
    try:
        ensure_watchlist_table(conn)
        rows = conn.execute(
            '''
            SELECT code
            FROM watchlist
            WHERE enabled=1
            ORDER BY sort_order ASC, added_at ASC, code ASC
            '''
        ).fetchall()
        return [str(r['code']).strip().lower() for r in rows if str(r['code']).strip()]
    finally:
        conn.close()


def seed_default_if_empty(db_path, default_codes):
    conn = _connect(db_path)
    try:
        ensure_watchlist_table(conn)
        row = conn.execute('SELECT COUNT(*) AS c FROM watchlist WHERE enabled=1').fetchone()
        count = int(row['c'] or 0)
        if count <= 0:
            for idx, code in enumerate(list(default_codes or []), start=1):
                normalized = _normalize_code(code)
                if not normalized:
                    continue
                conn.execute(
                    '''
                    INSERT OR IGNORE INTO watchlist (code, name, enabled, sort_order)
                    VALUES (?,?,1,?)
                    ''',
                    (normalized, '', idx)
                )
        conn.commit()
    finally:
        conn.close()

