"""
Reset the played_songs table to the new schema (audio slider targets).

WARNING: This will DROP the played_songs table and all history.

Run:
  python app/assistant/database/migrations/reset_played_songs_table_audio_sliders.py
"""

from __future__ import annotations

import sqlite3
from pathlib import Path


def _get_db_path() -> Path:
    # Single source of truth for db location
    from app.models.base import get_database_uri

    uri = get_database_uri()  # sqlite:////path/to/emi.db
    if not uri.startswith("sqlite:///"):
        raise RuntimeError(f"Unsupported DB URI for reset script: {uri}")

    db_path = uri.replace("sqlite:///", "", 1)
    return Path(db_path)


CREATE_SQL = """
CREATE TABLE played_songs (
  id INTEGER PRIMARY KEY,
  title VARCHAR(500) NOT NULL,
  artist VARCHAR(500) NOT NULL,
  search_query VARCHAR(500),

  first_played_utc DATETIME NOT NULL,
  last_played_utc DATETIME NOT NULL,

  play_count_today INTEGER DEFAULT 1,
  play_count_week INTEGER DEFAULT 1,
  play_count_month INTEGER DEFAULT 1,
  play_count_year INTEGER DEFAULT 1,
  play_count_all_time INTEGER DEFAULT 1,

  -- Audio targets at time of pick (LLM sliders 0-100)
  last_energy_slider INTEGER,
  last_valence_slider INTEGER,
  last_loudness_slider INTEGER,
  last_speechiness_slider INTEGER,
  last_acousticness_slider INTEGER,
  last_instrumentalness_slider INTEGER,
  last_liveness_slider INTEGER,
  last_tempo_slider INTEGER,

  last_count_reset_date VARCHAR(10)
);
"""

INDEXES_SQL = [
    "CREATE UNIQUE INDEX idx_played_songs_title_artist ON played_songs(title, artist);",
    "CREATE INDEX idx_played_songs_last_played ON played_songs(last_played_utc);",
]


def main() -> int:
    db_path = _get_db_path()
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    print(f"[INFO] Using DB: {db_path}")

    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute("PRAGMA foreign_keys=OFF;")
        cur.execute("DROP TABLE IF EXISTS played_songs;")
        cur.execute(CREATE_SQL)
        for sql in INDEXES_SQL:
            cur.execute(sql)
        con.commit()
        print("[OK] played_songs reset complete.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())

