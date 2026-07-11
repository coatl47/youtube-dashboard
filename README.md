[README.md](https://github.com/user-attachments/files/29926575/README.md)
# 유튜브 댓글 여론 모니터링 — Python

기존 Streamlit 단일 파일을 확장한 코드가 아니라, 수집·분석·저장·표시를 분리해 다시 만든 구현입니다.

## 핵심 원칙

- 현재 조회수로 과거 추이를 만들지 않습니다. `video_metric_snapshots`에 실제 관측값만 저장합니다.
- 댓글 본문이 아니라 YouTube `comment_id`로 중복을 제거합니다.
- `textFormat=plainText`를 사용하고 댓글·답글·작성시각·좋아요를 저장합니다.
- AI는 원문을 다시 출력하지 않고 `comment_id`와 구조화된 enum 결과만 반환합니다.
- 분석 결과는 본문 해시, 모델, 프롬프트, taxonomy 버전으로 캐시합니다.
- Streamlit은 DB를 읽기만 하며 화면 요청이 YouTube/Gemini API를 직접 호출하지 않습니다.
- 모든 추이와 집계에 수집 범위·분모·부분 성공 상태를 함께 표시합니다.

## 구성

```text
monitoring/
  config.py       환경설정
  models.py       데이터 및 AI 스키마
  db.py           SQLite 스키마와 저장소
  youtube.py      YouTube 수집기
  analyzer.py     Gemini structured output 분석기
  pipeline.py     수집·분석 파이프라인
  cli.py          스케줄러에서 호출할 CLI
dashboard.py      읽기 전용 Streamlit 대시보드
tests/            핵심 회귀 테스트
```

## 설치

```bash
cd python_monitoring
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
```

`.env`에 `YOUTUBE_API_KEY`와 `GEMINI_API_KEY`를 설정합니다. 비밀키는 저장소에 커밋하지 않습니다.

## 실행 순서

```bash
# DB 생성
yt-monitor init

# 영상 통계와 댓글 수집
yt-monitor collect "https://www.youtube.com/watch?v=VIDEO_ID"

# 신규·수정 댓글만 분석
yt-monitor analyze --limit 200

# 수집과 분석을 연속 실행
yt-monitor run "https://www.youtube.com/watch?v=VIDEO_ID" --limit 200

# 대시보드
streamlit run dashboard.py
```

운영에서는 `yt-monitor run ...`을 cron, GitHub Actions 또는 별도 스케줄러에서 실행하고 Streamlit은 별도 프로세스로 운영합니다.

## 수집 범위

기본값은 관련도 2페이지 + 최신 2페이지이며 댓글 ID로 합칩니다. 이는 전체 여론의 대표 표본이 아닐 수 있으므로 대시보드에 수집 전략과 커버리지를 표시합니다. `MAX_COMMENT_PAGES`로 페이지 예산을 조절할 수 있습니다.

답글을 포함하면 `commentThreads.list`에 포함되지 않은 나머지 답글을 `comments.list(parentId=...)`로 추가 수집합니다. API 쿼터와 실행시간을 고려해 운영 환경에서 상한을 설정하세요.

## 정기 수집

조회수 추이를 만들려면 같은 영상을 반복 수집해야 합니다. 예:

```cron
*/30 * * * * cd /path/python_monitoring && .venv/bin/yt-monitor run "VIDEO_URL" --limit 200
```

모든 시각은 DB에 UTC로 저장하고 화면에서 KST로 변환합니다.

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 다음 운영 확장

- PostgreSQL과 작업 큐로 교체
- 수집·분석 작업 상태와 dead-letter 관리
- taxonomy 및 수동 검토 이력 관리
- 채널 소유 권한이 있으면 YouTube Analytics API 일별 지표 연동
- 인증, 역할별 접근, 알림 임계값, 개인정보 최소화 정책 추가
