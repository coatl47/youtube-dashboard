from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable, Iterator

from .models import AnalysisItem, Comment, MetricSnapshot, Video


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS videos (
  video_id TEXT PRIMARY KEY,
  channel_id TEXT,
  channel_title TEXT NOT NULL,
  title TEXT NOT NULL,
  published_at_utc TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  last_seen_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS video_metric_snapshots (
  video_id TEXT NOT NULL REFERENCES videos(video_id),
  observed_at_utc TEXT NOT NULL,
  view_count INTEGER NOT NULL,
  like_count INTEGER,
  comment_count INTEGER,
  PRIMARY KEY(video_id, observed_at_utc)
);

CREATE TABLE IF NOT EXISTS comments (
  comment_id TEXT PRIMARY KEY,
  video_id TEXT NOT NULL REFERENCES videos(video_id),
  thread_id TEXT NOT NULL,
  parent_id TEXT,
  is_reply INTEGER NOT NULL,
  text_plain TEXT NOT NULL,
  text_sha256 TEXT NOT NULL,
  published_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  like_count INTEGER NOT NULL,
  reply_count INTEGER NOT NULL,
  first_seen_at_utc TEXT NOT NULL,
  last_seen_at_utc TEXT NOT NULL,
  deleted_at_utc TEXT
);

CREATE TABLE IF NOT EXISTS collection_runs (
  run_id TEXT PRIMARY KEY,
  video_id TEXT,
  strategy TEXT NOT NULL,
  started_at_utc TEXT NOT NULL,
  completed_at_utc TEXT,
  pages INTEGER NOT NULL DEFAULT 0,
  quota_units INTEGER NOT NULL DEFAULT 0,
  fetched INTEGER NOT NULL DEFAULT 0,
  unique_count INTEGER NOT NULL DEFAULT 0,
  status TEXT NOT NULL,
  error_code TEXT
);

CREATE TABLE IF NOT EXISTS sample_members (
  run_id TEXT NOT NULL REFERENCES collection_runs(run_id),
  comment_id TEXT NOT NULL REFERENCES comments(comment_id),
  stratum TEXT NOT NULL,
  rank INTEGER NOT NULL,
  PRIMARY KEY(run_id, comment_id, stratum)
);

CREATE TABLE IF NOT EXISTS comment_analyses (
  comment_id TEXT NOT NULL REFERENCES comments(comment_id),
  text_sha256 TEXT NOT NULL,
  sentiment TEXT NOT NULL,
  target TEXT NOT NULL,
  topic TEXT NOT NULL,
  keyword TEXT NOT NULL,
  spam INTEGER NOT NULL,
  confidence REAL NOT NULL,
  risk TEXT NOT NULL,
  rationale TEXT NOT NULL,
  model TEXT NOT NULL,
  prompt_version TEXT NOT NULL,
  taxonomy_version TEXT NOT NULL,
  status TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  PRIMARY KEY(comment_id, text_sha256, model, prompt_version, taxonomy_version)
);

CREATE INDEX IF NOT EXISTS idx_comments_video ON comments(video_id, published_at_utc);
CREATE INDEX IF NOT EXISTS idx_analysis_lookup ON comment_analyses(comment_id, text_sha256, status);
"""


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise ValueError("UTC datetime must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class Repository:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def initialize(self) -> None:
        with self.connect() as con:
            con.executescript(SCHEMA)

    def upsert_video(self, video: Video, seen_at: datetime) -> None:
        with self.connect() as con:
            con.execute(
                """INSERT INTO videos VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(video_id) DO UPDATE SET
                  channel_id=excluded.channel_id, channel_title=excluded.channel_title,
                  title=excluded.title, published_at_utc=excluded.published_at_utc,
                  canonical_url=excluded.canonical_url, last_seen_at_utc=excluded.last_seen_at_utc""",
                (video.video_id, video.channel_id, video.channel_title, video.title,
                 iso(video.published_at), video.canonical_url, iso(seen_at)),
            )

    def add_snapshot(self, snapshot: MetricSnapshot) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO video_metric_snapshots VALUES (?, ?, ?, ?, ?)",
                (snapshot.video_id, iso(snapshot.observed_at), snapshot.view_count,
                 snapshot.like_count, snapshot.comment_count),
            )

    def start_run(self, strategy: str) -> str:
        run_id = str(uuid.uuid4())
        with self.connect() as con:
            con.execute(
                "INSERT INTO collection_runs(run_id, strategy, started_at_utc, status) VALUES (?, ?, ?, 'running')",
                (run_id, strategy, iso(utc_now())),
            )
        return run_id

    def finish_run(self, run_id: str, *, video_id: str | None, pages: int, quota_units: int,
                   fetched: int, unique: int, status: str, error_code: str | None = None) -> None:
        with self.connect() as con:
            con.execute(
                """UPDATE collection_runs SET video_id=?, completed_at_utc=?, pages=?, quota_units=?,
                fetched=?, unique_count=?, status=?, error_code=? WHERE run_id=?""",
                (video_id, iso(utc_now()), pages, quota_units, fetched, unique, status, error_code, run_id),
            )

    def upsert_comments(self, run_id: str, comments: Iterable[Comment], seen_at: datetime) -> int:
        rows = list(comments)
        with self.connect() as con:
            for item in rows:
                con.execute(
                    """INSERT INTO comments VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    ON CONFLICT(comment_id) DO UPDATE SET
                      text_plain=excluded.text_plain, text_sha256=excluded.text_sha256,
                      updated_at_utc=excluded.updated_at_utc, like_count=excluded.like_count,
                      reply_count=excluded.reply_count, last_seen_at_utc=excluded.last_seen_at_utc,
                      deleted_at_utc=NULL""",
                    (item.comment_id, item.video_id, item.thread_id, item.parent_id, int(item.is_reply),
                     item.text, text_hash(item.text), iso(item.published_at), iso(item.updated_at),
                     item.like_count, item.reply_count, iso(seen_at), iso(seen_at)),
                )
                con.execute(
                    "INSERT OR IGNORE INTO sample_members VALUES (?, ?, ?, ?)",
                    (run_id, item.comment_id, item.stratum, item.rank),
                )
        return len(rows)

    def pending_analysis(self, model: str, prompt_version: str, taxonomy_version: str, limit: int) -> list[dict]:
        with self.connect() as con:
            rows = con.execute(
                """SELECT c.comment_id, c.text_plain, c.text_sha256
                FROM comments c
                WHERE c.deleted_at_utc IS NULL AND NOT EXISTS (
                  SELECT 1 FROM comment_analyses a
                  WHERE a.comment_id=c.comment_id AND a.text_sha256=c.text_sha256
                    AND a.model=? AND a.prompt_version=? AND a.taxonomy_version=? AND a.status='success'
                ) ORDER BY c.published_at_utc DESC LIMIT ?""",
                (model, prompt_version, taxonomy_version, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def save_analyses(self, source: dict[str, dict], items: Iterable[AnalysisItem], *, model: str,
                      prompt_version: str, taxonomy_version: str) -> None:
        created = iso(utc_now())
        with self.connect() as con:
            for item in items:
                sha = source[item.comment_id]["text_sha256"]
                con.execute(
                    """INSERT OR REPLACE INTO comment_analyses VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'success', ?)""",
                    (item.comment_id, sha, item.sentiment, item.target, item.topic, item.keyword,
                     int(item.spam), item.confidence, item.risk, item.rationale, model,
                     prompt_version, taxonomy_version, created),
                )

    def list_videos(self) -> list[dict]:
        with self.connect() as con:
            rows = con.execute("SELECT * FROM videos ORDER BY published_at_utc DESC").fetchall()
        return [dict(row) for row in rows]

    def dashboard_rows(self, video_id: str) -> tuple[list[dict], list[dict], dict | None]:
        with self.connect() as con:
            history = [dict(row) for row in con.execute(
                "SELECT * FROM video_metric_snapshots WHERE video_id=? ORDER BY observed_at_utc", (video_id,)
            ).fetchall()]
            comments = [dict(row) for row in con.execute(
                """SELECT c.comment_id, c.text_plain, c.published_at_utc, c.like_count, c.reply_count,
                a.sentiment, a.topic, a.keyword, a.risk, a.confidence, a.spam
                FROM comments c JOIN comment_analyses a ON a.comment_id=c.comment_id AND a.text_sha256=c.text_sha256
                WHERE c.video_id=? AND c.deleted_at_utc IS NULL AND a.status='success'
                ORDER BY c.published_at_utc DESC""", (video_id,)
            ).fetchall()]
            run = con.execute(
                "SELECT * FROM collection_runs WHERE video_id=? ORDER BY completed_at_utc DESC LIMIT 1", (video_id,)
            ).fetchone()
        return history, comments, dict(run) if run else None
