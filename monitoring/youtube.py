from __future__ import annotations

import random
import time
from datetime import UTC, datetime
from typing import Iterator
from urllib.parse import parse_qs, urlparse

from .models import Comment, MetricSnapshot, Video

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtu.be"}


def extract_video_id(value: str) -> str:
    value = value.strip()
    if len(value) == 11 and all(ch.isalnum() or ch in "_-" for ch in value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in YOUTUBE_HOSTS:
        raise ValueError("지원하는 YouTube URL이 아닙니다.")
    if parsed.hostname in {"youtu.be", "www.youtu.be"}:
        candidate = parsed.path.strip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    elif parsed.path.startswith(("/shorts/", "/embed/")):
        candidate = parsed.path.strip("/").split("/")[1]
    else:
        candidate = ""
    if len(candidate) != 11 or not all(ch.isalnum() or ch in "_-" for ch in candidate):
        raise ValueError("유효한 YouTube 영상 ID를 찾지 못했습니다.")
    return candidate


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


class YouTubeClient:
    """A request-scoped YouTube Data API client with bounded retries and quota counters."""

    def __init__(self, api_key: str, *, max_retries: int = 3):
        from googleapiclient.discovery import build

        self._service = build("youtube", "v3", developerKey=api_key, cache_discovery=False)
        self.max_retries = max_retries
        self.pages = 0
        self.quota_units = 0

    def _execute(self, request):
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                result = request.execute()
                self.pages += 1
                self.quota_units += 1
                return result
            except Exception as exc:  # googleapiclient exposes several transport exception types
                last_error = exc
                status = getattr(getattr(exc, "resp", None), "status", None)
                if status not in {429, 500, 502, 503, 504} or attempt + 1 >= self.max_retries:
                    raise
                time.sleep(min(8.0, (2 ** attempt) + random.random()))
        raise RuntimeError("YouTube API request failed") from last_error

    def fetch_video(self, video_id: str, observed_at: datetime) -> tuple[Video, MetricSnapshot]:
        response = self._execute(
            self._service.videos().list(part="snippet,statistics", id=video_id, maxResults=1)
        )
        if not response.get("items"):
            raise LookupError("영상이 없거나 비공개 상태입니다.")
        item = response["items"][0]
        snippet, stats = item["snippet"], item.get("statistics", {})
        video = Video(
            video_id=video_id,
            channel_id=snippet.get("channelId"),
            channel_title=snippet.get("channelTitle", "알 수 없는 채널"),
            title=snippet["title"],
            published_at=parse_time(snippet["publishedAt"]),
            canonical_url=f"https://www.youtube.com/watch?v={video_id}",
        )
        snapshot = MetricSnapshot(
            video_id=video_id,
            observed_at=observed_at,
            view_count=int(stats.get("viewCount", 0)),
            like_count=int(stats["likeCount"]) if "likeCount" in stats else None,
            comment_count=int(stats["commentCount"]) if "commentCount" in stats else None,
        )
        return video, snapshot

    def iter_comments(self, video_id: str, *, order: str, max_pages: int,
                      include_replies: bool) -> Iterator[Comment]:
        token: str | None = None
        rank = 0
        for _ in range(max_pages):
            kwargs = dict(
                part="snippet,replies" if include_replies else "snippet",
                videoId=video_id,
                maxResults=100,
                order=order,
                textFormat="plainText",
            )
            if token:
                kwargs["pageToken"] = token
            response = self._execute(self._service.commentThreads().list(**kwargs))
            for thread in response.get("items", []):
                thread_id = thread["id"]
                top = thread["snippet"]["topLevelComment"]
                top_snippet = top["snippet"]
                rank += 1
                yield self._to_comment(video_id, thread_id, top["id"], None, False,
                                       top_snippet, int(thread["snippet"].get("totalReplyCount", 0)), order, rank)

                if not include_replies:
                    continue
                inline = thread.get("replies", {}).get("comments", [])
                seen_reply_ids = set()
                for reply in inline:
                    seen_reply_ids.add(reply["id"])
                    rank += 1
                    yield self._to_comment(video_id, thread_id, reply["id"], top["id"], True,
                                           reply["snippet"], 0, order, rank)

                total_replies = int(thread["snippet"].get("totalReplyCount", 0))
                if total_replies > len(inline):
                    for reply in self._iter_all_replies(video_id, thread_id, top["id"], order, rank):
                        if reply.comment_id not in seen_reply_ids:
                            rank += 1
                            yield reply

            token = response.get("nextPageToken")
            if not token:
                break

    def _iter_all_replies(self, video_id: str, thread_id: str, parent_id: str,
                          stratum: str, start_rank: int) -> Iterator[Comment]:
        token: str | None = None
        rank = start_rank
        while True:
            kwargs = dict(part="snippet", parentId=parent_id, maxResults=100, textFormat="plainText")
            if token:
                kwargs["pageToken"] = token
            response = self._execute(self._service.comments().list(**kwargs))
            for item in response.get("items", []):
                rank += 1
                yield self._to_comment(video_id, thread_id, item["id"], parent_id, True,
                                       item["snippet"], 0, stratum, rank)
            token = response.get("nextPageToken")
            if not token:
                break

    @staticmethod
    def _to_comment(video_id: str, thread_id: str, comment_id: str, parent_id: str | None,
                    is_reply: bool, snippet: dict, reply_count: int, stratum: str, rank: int) -> Comment:
        return Comment(
            comment_id=comment_id,
            video_id=video_id,
            thread_id=thread_id,
            parent_id=parent_id,
            is_reply=is_reply,
            text=(snippet.get("textDisplay") or "").strip(),
            published_at=parse_time(snippet["publishedAt"]),
            updated_at=parse_time(snippet.get("updatedAt", snippet["publishedAt"])),
            like_count=int(snippet.get("likeCount", 0)),
            reply_count=reply_count,
            stratum=stratum,
            rank=rank,
        )
