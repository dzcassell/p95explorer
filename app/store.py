import json
import os
import sqlite3
from pathlib import Path

DB = Path(os.environ.get('P95_DATA_DIR', 'data')) / 'explorer.sqlite3'


class ClosingConnection(sqlite3.Connection):
    def __exit__(self,*args):
        try:return super().__exit__(*args)
        finally:self.close()


def connect():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB, timeout=30, factory=ClosingConnection)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.executescript('''
    CREATE TABLE IF NOT EXISTS sites (tenant TEXT, id TEXT, name TEXT, region TEXT, capacity REAL, type TEXT,
      PRIMARY KEY(tenant,id));
    CREATE TABLE IF NOT EXISTS samples (tenant TEXT, site_id TEXT, ts INTEGER, up REAL, down REAL,
      PRIMARY KEY(tenant,site_id,ts));
    CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
    ''')
    columns = {r[1] for r in conn.execute('PRAGMA table_info(sites)')}
    if 'source' not in columns:
        conn.execute("ALTER TABLE sites ADD COLUMN source TEXT DEFAULT 'legacy-unverified'")
        conn.commit()
    return conn


def setting(key, value=None):
    with connect() as db:
        if value is not None:
            db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
        row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else None


def save(tenant, sites, samples):
    with connect() as db:
        for s in sites:
            db.execute('''INSERT INTO sites(tenant,id,name,region,capacity,type,source) VALUES (?,?,?,?,?,?,?) ON CONFLICT(tenant,id)
              DO UPDATE SET name=excluded.name, type=excluded.type, source=excluded.source''',
              (tenant, str(s['id']), s['name'], s.get('region', 'Unassigned'), s.get('capacity'), s.get('type', 'Unknown'), s.get('source', 'csv-import')))
        db.executemany('INSERT OR REPLACE INTO samples VALUES (?,?,?,?,?)',
                       [(tenant, str(s['site_id']), s['ts'], s['up'], s['down']) for s in samples])


def dataset(tenant, start, end):
    with connect() as db:
        sites = [dict(r) for r in db.execute('SELECT * FROM sites WHERE tenant=? ORDER BY name', (tenant,))]
        samples = [dict(r) for r in db.execute('SELECT site_id,ts,up,down FROM samples WHERE tenant=? AND ts>=? AND ts<? ORDER BY ts', (tenant,start,end))]
    return sites, samples


def months(tenant):
    with connect() as db:
        return [r[0] for r in db.execute("SELECT DISTINCT strftime('%Y-%m',ts,'unixepoch') AS month FROM samples WHERE tenant=? ORDER BY month DESC", (tenant,))]
