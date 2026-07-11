from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    db_path: Path
    youtube_api_key: str | None
    gemini_api_key: str | None
    gemini_model: str
    max_comment_pages: int
    include_replies: bool
    analysis_batch_size: int
    prompt_version: str = "sentiment-v1"
    taxonomy_version: str = "nps-topics-v1"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            db_path=Path(os.getenv("MONITOR_DB_PATH", "data/monitoring.sqlite3")),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY") or None,
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.5-flash"),
            max_comment_pages=max(1, int(os.getenv("MAX_COMMENT_PAGES", "2"))),
            include_replies=_bool("INCLUDE_REPLIES", True),
            analysis_batch_size=max(1, min(50, int(os.getenv("ANALYSIS_BATCH_SIZE", "20")))),
        )

    def require_youtube_key(self) -> str:
        if not self.youtube_api_key:
            raise RuntimeError("YOUTUBE_API_KEY가 설정되지 않았습니다.")
        return self.youtube_api_key

    def require_gemini_key(self) -> str:
        if not self.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")
        return self.gemini_api_key
