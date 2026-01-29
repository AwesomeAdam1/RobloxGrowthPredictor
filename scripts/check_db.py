import sqlite3

DB_PATH = "data/snapshots.sqlite"

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM snapshots;")
print("rows:", cur.fetchone()[0])

cur.execute("""
  SELECT ts_utc, game_id, current_players, visits, favorites, title
  FROM snapshots
  ORDER BY id DESC
  LIMIT 10;
""")
for row in cur.fetchall():
    print(row)

conn.close()