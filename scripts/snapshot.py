import os
import time
import json
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

import requests


DB_PATH = os.path.join("data", "snapshots.sqlite")
GAME_IDS_PATH = "game_ids.txt"

# Be polite. If you get rate-limited, increase this.
SLEEP_BETWEEN_REQUESTS_SEC = 0.25


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_game_ids(path: str) -> List[int]:
    ids: List[int] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ids.append(int(line))
    if not ids:
        raise ValueError("game_ids.txt is empty. Add some game IDs (one per line).")
    return ids


def ensure_db(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts_utc TEXT NOT NULL,
            game_id INTEGER NOT NULL,

            current_players INTEGER,
            visits INTEGER,
            favorites INTEGER,
            upvotes INTEGER,
            downvotes INTEGER,

            title TEXT,
            description TEXT,
            thumbnail_url TEXT,

            raw_json TEXT
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_snapshots_game_ts ON snapshots(game_id, ts_utc);")
    conn.commit()

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "roblox-growth-predictor/0.1 (educational project)"
})

# TODO Universe API can be grabbed 50 at a time. 
# TODO Fetch MEDIA for data as well
def fetch_game_public_info(game_id: int) -> Dict[str, Any]:
    """
    Return dict with fields like:
      title, description, visits, favorites, upvotes, downvotes, thumbnail_url
    """
    # fetches universe id from game id
    universe_id_url = f"https://apis.roblox.com/universes/v1/places/{game_id}/universe"
    response = SESSION.get(universe_id_url)
    response.raise_for_status()
    universe_id = response.json()["universeId"]
    print(universe_id)

    game_place_info_url = f"https://games.roblox.com/v1/games?universeIds={universe_id}"
    response = SESSION.get(game_place_info_url)
    response.raise_for_status()
    game_place_info = response.json()
    print(game_place_info)

    data = game_place_info.get("data", [])
    g = data[0] if data else {}

    votes_url = f"https://games.roblox.com/v1/games/votes?universeIds={universe_id}"
    response = SESSION.get(votes_url)
    response.raise_for_status()
    votes_info = response.json()
    print(votes_info)

    votes_data = votes_info.get("data", [])
    votes = votes_data[0] if votes_data else {}

    return {
        "title": g.get("name"),
        "ccu": g.get("playing"),
        "description": g.get("description"),
        "visits": g.get("visits"),
        "favorites": g.get("favoritedCount"),
        "upvotes": votes.get("upVotes"),
        "downvotes": votes.get("downVotes"),
        "thumbnail_url": None,
        "raw": g
    }


# -----------------------------
# Main snapshot routine
# -----------------------------
def take_snapshot(game_ids: List[int]) -> int:
    os.makedirs("data", exist_ok=True)
    ts = utc_now_iso()

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_db(conn)

        inserted = 0
        for i, gid in enumerate(game_ids):
            try:
                info = fetch_game_public_info(gid)

                row = {
                    "ts_utc": ts,
                    "game_id": gid,
                    "current_players": info.get("ccu"),
                    "visits": info.get("visits"),
                    "favorites": info.get("favorites"),
                    "upvotes": info.get("upvotes"),
                    "downvotes": info.get("downvotes"),
                    "title": info.get("title"),
                    "description": info.get("description"),
                    "thumbnail_url": info.get("thumbnail_url"),
                    "raw_json": json.dumps(info.get("raw", info), ensure_ascii=False),
                }

                conn.execute("""
                    INSERT INTO snapshots (
                        ts_utc, game_id,
                        current_players, visits, favorites, upvotes, downvotes,
                        title, description, thumbnail_url,
                        raw_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    row["ts_utc"], row["game_id"],
                    row["current_players"], row["visits"], row["favorites"], row["upvotes"], row["downvotes"],
                    row["title"], row["description"], row["thumbnail_url"],
                    row["raw_json"]
                ))
                inserted += 1

            except Exception as e:
                print(f"[WARN] game_id={gid} failed: {e}")

            time.sleep(SLEEP_BETWEEN_REQUESTS_SEC)

        conn.commit()
        print(f"[OK] {ts}: inserted {inserted}/{len(game_ids)} snapshots into {DB_PATH}")
        return inserted
    finally:
        conn.close()


if __name__ == "__main__":
    ids = read_game_ids(GAME_IDS_PATH)
    take_snapshot(ids)