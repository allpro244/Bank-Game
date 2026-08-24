"""Save-game persistence: SQLite, multiple named saves, autosave snapshots,
rollback to any stored day.

The entire simulation state is a JSON-serializable dict (money is integer
cents, RNG states are integer lists), so a snapshot is just gzip(json).
Autosave writes a snapshot after every advance; we keep every quarter-end
plus the most recent snapshots, so you can roll back a bad decision.
"""

import gzip
import json
import os
import sqlite3
import time

DB_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "saves.db") if "__file__" in globals() else "saves.db"

KEEP_RECENT = 40          # most recent snapshots kept per save
SCHEMA = """
CREATE TABLE IF NOT EXISTS saves (
    name TEXT PRIMARY KEY,
    seed INTEGER NOT NULL,
    created REAL NOT NULL,
    last_played REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshots (
    save_name TEXT NOT NULL,
    day_index INTEGER NOT NULL,
    date TEXT NOT NULL,
    quarter_end INTEGER NOT NULL DEFAULT 0,
    ts REAL NOT NULL,
    blob BLOB NOT NULL,
    PRIMARY KEY (save_name, day_index)
);
"""


class Store:
    def __init__(self, path=None):
        self.path = path or os.environ.get("BANKGAME_DB", DB_FILE)
        self.conn = sqlite3.connect(self.path, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    # ---- saves ----
    def list_saves(self):
        cur = self.conn.execute(
            "SELECT s.name, s.seed, s.created, s.last_played, "
            " (SELECT MAX(day_index) FROM snapshots WHERE save_name=s.name), "
            " (SELECT date FROM snapshots WHERE save_name=s.name "
            "  ORDER BY day_index DESC LIMIT 1) "
            "FROM saves s ORDER BY s.last_played DESC")
        out = []
        for name, seed, created, played, day, date in cur.fetchall():
            out.append({"name": name, "seed": seed, "created": created,
                        "last_played": played, "day_index": day or 0,
                        "date": date or ""})
        return out

    def create_save(self, name, seed):
        now = time.time()
        self.conn.execute(
            "INSERT OR REPLACE INTO saves(name, seed, created, last_played) "
            "VALUES (?,?,?,?)", (name, seed, now, now))
        self.conn.commit()

    def delete_save(self, name):
        self.conn.execute("DELETE FROM snapshots WHERE save_name=?", (name,))
        self.conn.execute("DELETE FROM saves WHERE name=?", (name,))
        self.conn.commit()

    # ---- snapshots ----
    def snapshot(self, state):
        name = state["meta"]["name"]
        day = state["time"]["day_index"]
        date = state["time"]["date"]
        month = int(date[5:7])
        qend = 1 if month in (1, 4, 7, 10) and int(date[8:10]) <= 3 else 0
        blob = gzip.compress(json.dumps(state, separators=(",", ":")).encode("utf-8"))
        self.conn.execute(
            "INSERT OR REPLACE INTO snapshots(save_name, day_index, date, "
            "quarter_end, ts, blob) VALUES (?,?,?,?,?,?)",
            (name, day, date, qend, time.time(), blob))
        self.conn.execute("UPDATE saves SET last_played=? WHERE name=?",
                          (time.time(), name))
        self._prune(name)
        self.conn.commit()

    def _prune(self, name):
        cur = self.conn.execute(
            "SELECT day_index FROM snapshots WHERE save_name=? AND quarter_end=0 "
            "ORDER BY day_index DESC", (name,))
        rows = [r[0] for r in cur.fetchall()]
        for day in rows[KEEP_RECENT:]:
            self.conn.execute(
                "DELETE FROM snapshots WHERE save_name=? AND day_index=?", (name, day))

    def list_snapshots(self, name):
        cur = self.conn.execute(
            "SELECT day_index, date, quarter_end FROM snapshots WHERE save_name=? "
            "ORDER BY day_index DESC LIMIT 200", (name,))
        return [{"day_index": d, "date": dt, "quarter_end": bool(q)}
                for d, dt, q in cur.fetchall()]

    def load(self, name, day_index=None):
        if day_index is None:
            cur = self.conn.execute(
                "SELECT blob FROM snapshots WHERE save_name=? "
                "ORDER BY day_index DESC LIMIT 1", (name,))
        else:
            cur = self.conn.execute(
                "SELECT blob FROM snapshots WHERE save_name=? AND day_index=?",
                (name, day_index))
        row = cur.fetchone()
        if row is None:
            return None
        state = json.loads(gzip.decompress(row[0]).decode("utf-8"))
        if day_index is not None:
            # rolling back: discard the future
            self.conn.execute(
                "DELETE FROM snapshots WHERE save_name=? AND day_index>?",
                (name, day_index))
            self.conn.commit()
        return state
