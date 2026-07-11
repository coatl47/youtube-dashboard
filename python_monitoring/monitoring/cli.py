from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

from .config import Settings
from .db import Repository
from .pipeline import analyze_pending, collect_video


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="yt-monitor")
    sub = result.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="SQLite schema 생성")
    collect = sub.add_parser("collect", help="영상 통계와 댓글 수집")
    collect.add_argument("video_url")
    analyze = sub.add_parser("analyze", help="미분석 댓글 AI 분류")
    analyze.add_argument("--limit", type=int, default=200)
    run = sub.add_parser("run", help="수집 후 AI 분류")
    run.add_argument("video_url")
    run.add_argument("--limit", type=int, default=200)
    return result


def main() -> None:
    load_dotenv()
    args = parser().parse_args()
    settings = Settings.from_env()
    repository = Repository(settings.db_path)
    repository.initialize()

    if args.command == "init":
        print(f"initialized: {settings.db_path}")
    elif args.command == "collect":
        print(json.dumps(collect_video(settings, repository, args.video_url).__dict__, ensure_ascii=False))
    elif args.command == "analyze":
        print(json.dumps({"analyzed": analyze_pending(settings, repository, limit=args.limit)}, ensure_ascii=False))
    elif args.command == "run":
        collection = collect_video(settings, repository, args.video_url)
        analyzed = analyze_pending(settings, repository, limit=args.limit)
        print(json.dumps({"collection": collection.__dict__, "analyzed": analyzed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
