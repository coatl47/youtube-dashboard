from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from monitoring.db import Repository, text_hash
from monitoring.models import AnalysisItem, Comment, MetricSnapshot, Video
from monitoring.youtube import extract_video_id


class VideoIdTests(unittest.TestCase):
    def test_supported_urls(self):
        expected = "EBLo0C-sj2w"
        self.assertEqual(extract_video_id(expected), expected)
        self.assertEqual(extract_video_id(f"https://youtu.be/{expected}?x=1"), expected)
        self.assertEqual(extract_video_id(f"https://www.youtube.com/watch?v={expected}"), expected)
        self.assertEqual(extract_video_id(f"https://youtube.com/shorts/{expected}"), expected)

    def test_rejects_untrusted_host(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://evil.example/watch?v=EBLo0C-sj2w")


class RepositoryTests(unittest.TestCase):
    def test_idempotent_comment_and_analysis_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Repository(Path(tmp) / "db.sqlite3")
            repo.initialize()
            now = datetime.now(UTC)
            video = Video("EBLo0C-sj2w", "channel", "채널", "제목", now, "https://youtu.be/EBLo0C-sj2w")
            repo.upsert_video(video, now)
            repo.add_snapshot(MetricSnapshot(video.video_id, now, 10, 2, 1))
            run = repo.start_run("test")
            comment = Comment("comment-1", video.video_id, "thread-1", None, False, "좋은 설명입니다", now, now, 3, 0, "time", 1)
            repo.upsert_comments(run, [comment, comment], now)
            repo.finish_run(run, video_id=video.video_id, pages=1, quota_units=1,
                            fetched=2, unique=1, status="success")

            pending = repo.pending_analysis("model", "prompt", "taxonomy", 10)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["text_sha256"], text_hash(comment.text))
            result = AnalysisItem(
                comment_id=comment.comment_id, sentiment="긍정", target="국민연금",
                topic="정보 공개", keyword="설명", spam=False, confidence=.91,
                risk="관찰", rationale="설명에 대한 긍정 반응",
            )
            repo.save_analyses({comment.comment_id: pending[0]}, [result], model="model",
                               prompt_version="prompt", taxonomy_version="taxonomy")
            self.assertEqual(repo.pending_analysis("model", "prompt", "taxonomy", 10), [])
            history, comments, last_run = repo.dashboard_rows(video.video_id)
            self.assertEqual(len(history), 1)
            self.assertEqual(len(comments), 1)
            self.assertEqual(last_run["status"], "success")


if __name__ == "__main__":
    unittest.main()
