"""Generate reader-friendly non-policy posts from curated high-demand topics."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

from blog_agent.config import load_settings
from blog_agent.editor import SeoEditorAgent
from blog_agent.images import ImageAgent
from blog_agent.models import Source, Topic
from blog_agent.publishers import MarkdownPublisher
from blog_agent.retrieval import FactRetriever
from blog_agent.writer import WriterAgent


POPULAR_TOPICS: dict[str, list[tuple[str, str]]] = {
    "생활": [
        ("여름 전기요금 줄이는 법", "에어컨, 제습기, 대기전력까지 한 번에 확인하는 절약 가이드"),
        ("장마철 제습기 사용법", "습도 관리와 전기요금을 함께 보는 실내 관리 팁"),
        ("에어컨 전기세 아끼는 설정", "온도, 풍량, 선풍기 병행 기준을 정리"),
        ("여름철 음식 보관법", "상하기 쉬운 식재료와 냉장고 정리 포인트"),
        ("알뜰폰 요금제 비교 기준", "데이터 사용량별로 요금제를 고르는 방법"),
        ("통신비 절약 체크리스트", "결합 할인, 선택약정, 알뜰폰 전환 전 확인할 점"),
        ("중고거래 사기 피하는 법", "입금 전 확인해야 할 안전 거래 신호"),
        ("자동차 보험료 절약 방법", "갱신 전 비교해야 할 특약과 할인 조건"),
        ("여름 휴가 준비물 리스트", "국내 여행 전 빠뜨리기 쉬운 물건 정리"),
        ("제철 과일 보관법", "여름 과일을 오래 먹기 위한 보관 기준"),
        ("실내 곰팡이 제거 순서", "장마철 집안 관리와 재발 방지 포인트"),
        ("초보자 걷기 운동 루틴", "무리하지 않고 습관을 만드는 생활 루틴"),
        ("보조금 신청 전 확인할 것", "조건, 기간, 증빙서류를 놓치지 않는 방법"),
        ("냉장고 전기요금 줄이는 법", "정리 방식과 온도 설정을 함께 보는 가이드"),
        ("여름 반려동물 관리", "더위와 산책 시간을 조절하는 생활 관리 팁"),
    ],
    "기술": [
        ("AI 노트북 고르는 기준", "NPU, 배터리, 메모리 기준을 쉽게 비교"),
        ("아이폰 배터리 오래 쓰는 법", "설정과 충전 습관을 중심으로 정리"),
        ("갤럭시 업데이트 전 확인할 점", "백업, 호환성, 새 기능 확인 순서"),
        ("ChatGPT 업무 자동화 활용법", "반복 업무를 줄이는 프롬프트와 도구 조합"),
        ("로컬 LLM 입문 가이드", "내 컴퓨터에서 AI 모델을 돌릴 때 보는 기준"),
        ("클라우드 저장공간 비교", "사진, 문서, 백업 용도별 선택 기준"),
        ("무선이어폰 노이즈캔슬링 비교", "출퇴근, 공부, 통화 기준으로 보는 선택법"),
        ("보조배터리 기내반입 기준", "여행 전 용량과 표기 단위를 확인하는 법"),
        ("피싱 문자 구별하는 법", "링크, 발신자, 결제 문구를 확인하는 기준"),
        ("와이파이 공유기 고르는 법", "집 크기와 기기 수에 맞춘 선택 기준"),
        ("태블릿 공부용 선택 기준", "필기, 영상, 문서 작업별 체크 포인트"),
        ("스마트워치 고르는 기준", "배터리, 운동 기록, 알림 기능 중심 비교"),
        ("USB-C 충전기 고르는 법", "와트 수와 PPS, 케이블 호환성 정리"),
        ("가정용 NAS 입문", "사진 백업과 개인 클라우드 구축 전 확인할 점"),
        ("AI 이미지 생성 도구 비교", "블로그 썸네일과 콘텐츠 제작 관점에서 보는 기준"),
    ],
    "핫이슈": [
        ("서울 성수 카페 동선", "리뷰에서 자주 언급되는 성수 카페 거리 포인트"),
        ("제주 장마 여행 코스", "비 오는 날에도 보기 좋은 실내외 코스"),
        ("부산 해운대 야경 코스", "저녁 산책과 사진 포인트를 함께 보는 코스"),
        ("강릉 커피거리 여행", "카페, 바다, 산책 동선을 묶은 하루 코스"),
        ("전주 한옥마을 먹거리", "방문 전 많이 검색하는 먹거리와 동선"),
        ("여수 밤바다 여행", "저녁 시간대에 보기 좋은 이동 코스"),
        ("경주 황리단길 코스", "카페, 소품샵, 유적지를 함께 보는 방법"),
        ("대전 성심당 주변 코스", "빵집 방문과 함께 묶기 좋은 주변 동선"),
        ("인천 차이나타운 당일치기", "먹거리와 개항장 거리를 함께 보는 코스"),
        ("춘천 당일치기 여행", "닭갈비, 호수, 산책 코스를 묶은 일정"),
        ("속초 중앙시장 먹거리", "시장 방문 전 알아두면 좋은 인기 메뉴"),
        ("통영 케이블카 여행", "전망, 시장, 항구 동선을 함께 정리"),
        ("남해 독일마을 코스", "사진 포인트와 드라이브 동선을 중심으로"),
        ("포항 영일대 야경", "저녁 산책과 주변 볼거리를 묶은 코스"),
        ("수원 화성 산책 코스", "성곽길과 행궁동을 함께 보는 방법"),
    ],
}


def load_seen_keywords(state_dir: Path) -> set[str]:
    path = state_dir / "published_keywords.json"
    if not path.exists():
        return set()
    return set(json.loads(path.read_text(encoding="utf-8")))


def remember_keywords(state_dir: Path, keywords: list[str]) -> None:
    path = state_dir / "published_keywords.json"
    seen = load_seen_keywords(state_dir)
    seen.update(keyword.lower() for keyword in keywords)
    path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")


def existing_text(posts_dir: Path) -> str:
    chunks = []
    for path in posts_dir.glob("*.md"):
        chunks.append(path.stem.lower())
        try:
            chunks.append(path.read_text(encoding="utf-8").split("---", 2)[1].lower())
        except Exception:
            continue
    return "\n".join(chunks)


def build_topics(per_category: int, settings) -> list[Topic]:
    seen = load_seen_keywords(settings.state_dir)
    existing = existing_text(settings.output_dir)
    topics: list[Topic] = []
    for category, items in POPULAR_TOPICS.items():
        added = 0
        for keyword, hint in items:
            key = keyword.lower()
            if key in seen or key in existing:
                continue
            topics.append(
                Topic(
                    keyword=keyword,
                    title_hint=hint,
                    category=category,  # type: ignore[arg-type]
                    trend_score=90,
                    competition_score=0.42,
                    rationale="국내 블로그에서 반복 검색 수요가 높은 생활형·비교형 키워드",
                    sources=[
                        Source(
                            title=f"{keyword} 공개 정보 확인",
                            url="https://www.google.com/search?q=" + keyword.replace(" ", "+"),
                            summary=hint,
                            authority=2,
                        )
                    ],
                )
            )
            added += 1
            if added >= per_category:
                break
    return topics


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-category", type=int, default=10)
    parser.add_argument("--min-quality", type=float, default=60)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    settings.publisher = "markdown"
    writer = WriterAgent(settings)
    editor = SeoEditorAgent(settings)
    retriever = FactRetriever()
    images = ImageAgent(settings)
    publisher = MarkdownPublisher(settings.output_dir)

    topics = build_topics(args.per_category, settings)
    print(f"{len(topics)} non-policy topics selected")
    published: list[str] = []
    start = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=7)

    for index, topic in enumerate(topics):
        enriched = retriever.enrich(topic)
        draft = editor.improve(writer.write(enriched))
        draft = images.attach_cover(draft)
        draft.created_at = start - timedelta(minutes=index * 19)
        if draft.quality_score < args.min_quality:
            print(f"skip low quality {draft.quality_score:.1f}: {topic.keyword}")
            continue
        if args.dry_run:
            print(f"would publish [{topic.category}] {draft.title}")
            continue
        result = publisher.publish(draft)
        if result.ok:
            published.append(topic.keyword)
            print(f"+ [{topic.category}] {draft.title}")
        else:
            print(f"! {topic.keyword}: {result.message}")

    if published and not args.dry_run:
        remember_keywords(settings.state_dir, published)
    print(f"\npublished {len(published)} non-policy posts")


if __name__ == "__main__":
    main()
