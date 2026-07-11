from __future__ import annotations

from datetime import UTC, datetime

from .analyzer import GeminiAnalyzer
from .config import Settings
from .db import Repository
from .models import CollectionResult
from .youtube import YouTubeClient, extract_video_id


def collect_video(settings: Settings, repository: Repository, video_url: str) -> CollectionResult:
    video_id = extract_video_id(video_url)
    run_id = repository.start_run("relevance+time; bounded pages; comment_id dedupe")
    client = YouTubeClient(settings.require_youtube_key())
    observed_at = datetime.now(UTC)
    fetched = []
    errors: list[str] = []
    try:
        video, snapshot = client.fetch_video(video_id, observed_at)
        repository.upsert_video(video, observed_at)
        repository.add_snapshot(snapshot)
        for order in ("relevance", "time"):
            try:
                fetched.extend(client.iter_comments(
                    video_id,
                    order=order,
                    max_pages=settings.max_comment_pages,
                    include_replies=settings.include_replies,
                ))
            except Exception as exc:
                errors.append(f"{order}:{type(exc).__name__}")

        unique = {}
        for comment in fetched:
            if comment.text:
                unique.setdefault(comment.comment_id, comment)
        repository.upsert_comments(run_id, unique.values(), observed_at)
        status = "failed" if errors and not unique else "partial" if errors else "success"
        repository.finish_run(
            run_id, video_id=video_id, pages=client.pages, quota_units=client.quota_units,
            fetched=len(fetched), unique=len(unique), status=status,
            error_code=";".join(errors) or None,
        )
        return CollectionResult(video_id, len(fetched), len(unique), client.pages, client.quota_units, status)
    except Exception as exc:
        repository.finish_run(
            run_id, video_id=video_id, pages=client.pages, quota_units=client.quota_units,
            fetched=len(fetched), unique=0, status="failed", error_code=type(exc).__name__,
        )
        raise


def analyze_pending(settings: Settings, repository: Repository, *, limit: int = 200) -> int:
    analyzer = GeminiAnalyzer(settings.require_gemini_key(), settings.gemini_model)
    processed = 0
    while processed < limit:
        rows = repository.pending_analysis(
            settings.gemini_model, settings.prompt_version, settings.taxonomy_version,
            min(settings.analysis_batch_size, limit - processed),
        )
        if not rows:
            break
        items = analyzer.analyze(rows)
        source = {row["comment_id"]: row for row in rows}
        repository.save_analyses(
            source, items, model=settings.gemini_model,
            prompt_version=settings.prompt_version,
            taxonomy_version=settings.taxonomy_version,
        )
        processed += len(items)
    return processed
