"""
Convert a Stack Exchange XML data dump into a single SQLite database.

Usage:
    python scripts/build_superuser_db.py <xml_dir> <output_db>

Streams each XML file with iterparse (no full-file load), batches inserts,
creates indexes after data is loaded. Skips PostHistory (huge edit history).
"""

from __future__ import annotations

import sqlite3
import sys
import time
from pathlib import Path
from xml.etree import ElementTree as ET


SCHEMAS: dict[str, tuple[str, list[str]]] = {
    "users": (
        "Users.xml",
        [
            "Id INTEGER PRIMARY KEY", "Reputation INTEGER", "CreationDate TEXT",
            "DisplayName TEXT", "LastAccessDate TEXT", "WebsiteUrl TEXT",
            "Location TEXT", "AboutMe TEXT", "Views INTEGER",
            "UpVotes INTEGER", "DownVotes INTEGER", "AccountId INTEGER",
        ],
    ),
    "posts": (
        "Posts.xml",
        [
            "Id INTEGER PRIMARY KEY", "PostTypeId INTEGER", "AcceptedAnswerId INTEGER",
            "ParentId INTEGER", "CreationDate TEXT", "Score INTEGER",
            "ViewCount INTEGER", "Body TEXT", "OwnerUserId INTEGER",
            "LastEditDate TEXT", "LastActivityDate TEXT", "Title TEXT",
            "Tags TEXT", "AnswerCount INTEGER", "CommentCount INTEGER",
            "FavoriteCount INTEGER", "ClosedDate TEXT",
        ],
    ),
    "comments": (
        "Comments.xml",
        [
            "Id INTEGER PRIMARY KEY", "PostId INTEGER", "Score INTEGER",
            "Text TEXT", "CreationDate TEXT", "UserId INTEGER",
        ],
    ),
    "votes": (
        "Votes.xml",
        [
            "Id INTEGER PRIMARY KEY", "PostId INTEGER", "VoteTypeId INTEGER",
            "UserId INTEGER", "CreationDate TEXT", "BountyAmount INTEGER",
        ],
    ),
    "tags": (
        "Tags.xml",
        [
            "Id INTEGER PRIMARY KEY", "TagName TEXT", "Count INTEGER",
            "ExcerptPostId INTEGER", "WikiPostId INTEGER",
        ],
    ),
    "badges": (
        "Badges.xml",
        [
            "Id INTEGER PRIMARY KEY", "UserId INTEGER", "Name TEXT",
            "Date TEXT", "Class INTEGER", "TagBased INTEGER",
        ],
    ),
    "postlinks": (
        "PostLinks.xml",
        [
            "Id INTEGER PRIMARY KEY", "CreationDate TEXT", "PostId INTEGER",
            "RelatedPostId INTEGER", "LinkTypeId INTEGER",
        ],
    ),
}

INDEXES = [
    ("idx_posts_type", "posts(PostTypeId)"),
    ("idx_posts_owner", "posts(OwnerUserId)"),
    ("idx_posts_parent", "posts(ParentId)"),
    ("idx_posts_score", "posts(Score)"),
    ("idx_comments_postid", "comments(PostId)"),
    ("idx_comments_userid", "comments(UserId)"),
    ("idx_votes_postid", "votes(PostId)"),
    ("idx_votes_type", "votes(VoteTypeId)"),
    ("idx_badges_userid", "badges(UserId)"),
    ("idx_badges_name", "badges(Name)"),
    ("idx_tags_name", "tags(TagName)"),
    ("idx_users_rep", "users(Reputation)"),
]

BATCH_SIZE = 5000


def _col_names(cols: list[str]) -> list[str]:
    return [c.split()[0] for c in cols]


def _coerce(value: str | None, col_def: str) -> object:
    if value is None:
        return None
    if "INTEGER" in col_def:
        try:
            return int(value)
        except ValueError:
            return None
    return value


def load_table(con: sqlite3.Connection, xml_path: Path, table: str, columns: list[str]) -> int:
    col_names = _col_names(columns)
    placeholders = ",".join("?" * len(col_names))
    insert_sql = f"INSERT OR REPLACE INTO {table} ({','.join(col_names)}) VALUES ({placeholders})"

    cur = con.cursor()
    batch: list[tuple] = []
    count = 0
    started = time.time()
    last_report = started

    for _, elem in ET.iterparse(str(xml_path), events=("end",)):
        if elem.tag != "row":
            continue
        row = tuple(_coerce(elem.get(name), col) for name, col in zip(col_names, columns))
        batch.append(row)
        elem.clear()
        if len(batch) >= BATCH_SIZE:
            cur.executemany(insert_sql, batch)
            count += len(batch)
            batch.clear()
            now = time.time()
            if now - last_report > 10:
                rate = count / (now - started)
                print(f"  {table}: {count:,} rows ({rate:,.0f}/s)", flush=True)
                last_report = now

    if batch:
        cur.executemany(insert_sql, batch)
        count += len(batch)
    con.commit()
    print(f"  {table}: done — {count:,} rows in {time.time() - started:.1f}s", flush=True)
    return count


def main() -> None:
    if len(sys.argv) != 3:
        print("Usage: python scripts/build_superuser_db.py <xml_dir> <output_db>")
        sys.exit(2)

    xml_dir = Path(sys.argv[1])
    out_db = Path(sys.argv[2])
    if not xml_dir.is_dir():
        sys.exit(f"xml_dir not found: {xml_dir}")

    if out_db.exists():
        out_db.unlink()
    out_db.parent.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(str(out_db))
    con.execute("PRAGMA journal_mode = OFF")
    con.execute("PRAGMA synchronous = OFF")
    con.execute("PRAGMA temp_store = MEMORY")
    con.execute("PRAGMA cache_size = -200000")  # ~200 MB

    for table, (filename, columns) in SCHEMAS.items():
        xml_path = xml_dir / filename
        if not xml_path.exists():
            print(f"SKIP {table}: {xml_path} not found")
            continue
        cols_def = ",\n  ".join(columns)
        con.execute(f"CREATE TABLE {table} (\n  {cols_def}\n)")
        print(f"Loading {table} from {xml_path.name} ({xml_path.stat().st_size / 1024 / 1024:.0f} MB)...", flush=True)
        load_table(con, xml_path, table, columns)

    print("Creating indexes...", flush=True)
    for name, definition in INDEXES:
        started = time.time()
        con.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {definition}")
        print(f"  {name}: {time.time() - started:.1f}s", flush=True)

    print("Running ANALYZE...", flush=True)
    con.execute("ANALYZE")
    con.commit()
    con.close()

    size_mb = out_db.stat().st_size / 1024 / 1024
    print(f"\nDone. {out_db} ({size_mb:.0f} MB)")


if __name__ == "__main__":
    main()
