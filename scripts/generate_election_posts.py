"""Generate neutral election-result and pledge guide posts.

The posts intentionally avoid naming winners or parties unless a verified
source is parsed. This keeps the content useful without inventing election
facts when public datasets are still being updated.
"""
from __future__ import annotations

import argparse
import json
import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from blog_agent.config import load_settings
from blog_agent.editor import SeoEditorAgent
from blog_agent.images import ImageAgent
from blog_agent.models import Draft, Source, Topic
from blog_agent.publishers import MarkdownPublisher


OFFICIAL_SOURCES = [
    Source(
        title="중앙선거관리위원회 정책공약마당",
        url="https://policy.nec.go.kr/",
        summary="후보자와 정당의 정책·공약을 선거별, 지역별로 확인할 수 있는 공식 서비스입니다.",
        authority=5,
    ),
    Source(
        title="중앙선거관리위원회 선거통계시스템",
        url="https://info.nec.go.kr/",
        summary="개표 결과, 당선인, 득표율 등 선거 통계 확인에 쓰는 공식 서비스입니다.",
        authority=5,
    ),
    Source(
        title="중앙선거관리위원회 선거자료공개포털",
        url="https://data.nec.go.kr/",
        summary="선거 관련 공개 데이터와 통계 자료를 확인할 수 있는 공식 포털입니다.",
        authority=5,
    ),
]


REGIONS = [
    ("서울", "서울시장"),
    ("부산", "부산시장"),
    ("대구", "대구시장"),
    ("인천", "인천시장"),
    ("광주", "광주시장"),
    ("대전", "대전시장"),
    ("울산", "울산시장"),
    ("세종", "세종시장"),
    ("경기", "경기도지사"),
    ("강원", "강원도지사"),
    ("충북", "충청북도지사"),
    ("충남", "충청남도지사"),
    ("전북", "전북특별자치도지사"),
    ("전남", "전라남도지사"),
    ("경북", "경상북도지사"),
    ("경남", "경상남도지사"),
    ("제주", "제주특별자치도지사"),
]

SEOUL_DISTRICTS = [
    "종로구", "중구", "용산구", "성동구", "광진구", "동대문구", "중랑구",
    "성북구", "강북구", "도봉구", "노원구", "은평구", "서대문구", "마포구",
    "양천구", "강서구", "구로구", "금천구", "영등포구", "동작구", "관악구",
    "서초구", "강남구", "송파구", "강동구",
]

METRO_DISTRICTS = [
    ("부산", "해운대구"), ("부산", "수영구"), ("부산", "부산진구"), ("부산", "동래구"),
    ("대구", "중구"), ("대구", "수성구"), ("대구", "달서구"), ("대구", "동구"),
    ("인천", "연수구"), ("인천", "부평구"), ("인천", "남동구"), ("인천", "서구"),
    ("광주", "동구"), ("광주", "서구"), ("광주", "북구"), ("광주", "광산구"),
    ("대전", "유성구"), ("대전", "서구"), ("대전", "중구"), ("대전", "동구"),
    ("울산", "남구"), ("울산", "중구"), ("울산", "북구"), ("울산", "울주군"),
]

LOCAL_CITIES = [
    ("경기", "수원시장"), ("경기", "성남시장"), ("경기", "용인시장"), ("경기", "고양시장"),
    ("경기", "화성시장"), ("경기", "부천시장"), ("경기", "남양주시장"), ("경기", "안산시장"),
    ("강원", "춘천시장"), ("강원", "원주시장"), ("강원", "강릉시장"), ("강원", "속초시장"),
    ("충북", "청주시장"), ("충북", "충주시장"), ("충북", "제천시장"),
    ("충남", "천안시장"), ("충남", "아산시장"), ("충남", "공주시장"), ("충남", "서산시장"),
    ("전북", "전주시장"), ("전북", "군산시장"), ("전북", "익산시장"), ("전북", "남원시장"),
    ("전남", "목포시장"), ("전남", "여수시장"), ("전남", "순천시장"), ("전남", "나주시장"),
    ("경북", "포항시장"), ("경북", "경주시장"), ("경북", "구미시장"), ("경북", "안동시장"),
    ("경남", "창원시장"), ("경남", "진주시장"), ("경남", "김해시장"), ("경남", "양산시장"),
    ("제주", "제주시 지역 공약"), ("제주", "서귀포시 지역 공약"),
]

THEME_TOPICS = [
    ("교육감 당선인 공약", "교육·돌봄·학교 안전 공약을 공식자료로 확인하는 법"),
    ("청년 공약 확인법", "일자리, 주거, 창업 지원 공약을 따로 보는 방법"),
    ("교통 공약 확인법", "철도, 버스, 도로, 환승 정책을 구분해 읽는 기준"),
    ("부동산 공약 확인법", "주택 공급, 정비사업, 전세 지원 공약을 보는 기준"),
    ("복지 공약 확인법", "노인, 장애인, 아동·돌봄 공약을 구분하는 방법"),
    ("소상공인 공약 확인법", "상권, 임대료, 금융 지원 공약을 점검하는 순서"),
    ("기후·환경 공약 확인법", "탄소중립, 공원, 하천, 폐기물 정책을 읽는 기준"),
    ("문화관광 공약 확인법", "축제, 관광, 문화시설 공약의 실행 가능성을 보는 법"),
]


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


def make_slug(keyword: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in keyword).strip("-").lower()
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    suffix = hashlib.sha1(f"election-{keyword}-{datetime.now().date()}".encode()).hexdigest()[:8]
    return f"{cleaned}-{suffix}"


def build_topics(limit: int, settings) -> list[Topic]:
    seen = load_seen_keywords(settings.state_dir)
    existing = existing_text(settings.output_dir)
    items: list[tuple[str, str, str, str]] = []

    for region, office in REGIONS:
        items.append((f"{office} 당선인 공약", "정책", region, "광역단체장 공약과 선거 결과를 공식자료로 확인"))
        items.append((f"{region} 교육감 당선인 공약", "정책", region, "교육 공약과 학교 현안 중심으로 확인"))

    for district in SEOUL_DISTRICTS:
        items.append((f"서울 {district} 구청장 당선인 공약", "핫이슈", "서울", "동네 생활권 공약을 주민 관점에서 확인"))

    for city, district in METRO_DISTRICTS:
        items.append((f"{city} {district} 단체장 당선인 공약", "핫이슈", city, "구·군 단위 생활 공약과 지역 현안 확인"))

    for region, office in LOCAL_CITIES:
        items.append((f"{office} 당선인 공약", "핫이슈", region, "지역별 생활권 공약과 현안 확인"))

    for keyword, hint in THEME_TOPICS:
        items.append((f"지방선거 {keyword}", "정책", "전국", hint))

    topics: list[Topic] = []
    for keyword, category, region, hint in items:
        key = keyword.lower()
        if key in seen or key in existing:
            continue
        topic = Topic(
            keyword=keyword,
            title_hint=hint,
            category=category,  # type: ignore[arg-type]
            trend_score=88,
            competition_score=0.5,
            rationale="선거 직후 지역 유권자가 반복 검색하는 당선인 공약·지역 현안 정보",
            sources=OFFICIAL_SOURCES,
        )
        topic.sources.append(
            Source(
                title=f"{region} 지역 공식 누리집 검색",
                url=f"https://www.google.com/search?q={region}+당선인+공약+공식",
                summary="지자체 공식 발표나 인수위 자료가 공개되면 함께 대조해 확인합니다.",
                authority=2,
            )
        )
        topics.append(topic)
        if len(topics) >= limit:
            break
    return topics


def build_draft(topic: Topic, index: int) -> Draft:
    region = topic.keyword.split()[0]
    title = title_for(topic.keyword, index)
    body = f"""## 먼저 볼 것

{topic.keyword}은 선거 직후 지역 주민들이 가장 많이 찾는 정보 중 하나입니다. 다만 당선인 이름, 득표율, 세부 공약은 집계와 공개 시점에 따라 달라질 수 있어 공식 자료로 확인하는 순서가 중요합니다.

이 글은 특정 후보나 정당을 평가하려는 글이 아닙니다. {topic.keyword}을 볼 때 주민 입장에서 확인하면 좋은 항목을 정리한 안내입니다.

## 공식자료 확인 순서

| 순서 | 확인할 곳 | 볼 내용 |
| --- | --- | --- |
| 1 | 중앙선관위 선거통계시스템 | 당선인, 득표율, 선거구 결과 |
| 2 | 중앙선관위 정책공약마당 | 후보자별 주요 공약과 정책 자료 |
| 3 | 지자체 공식 누리집 | 인수위, 공약 이행계획, 보도자료 |
| 4 | 지방의회 회의록 | 예산과 조례로 실제 추진되는지 확인 |

## 공약을 읽을 때 나눠볼 기준

{topic.keyword}에서 가장 먼저 볼 부분은 생활에 바로 닿는 공약입니다. 교통, 주거, 돌봄, 교육, 상권, 안전은 체감도가 크고 예산 편성 여부도 비교적 빨리 드러납니다.

- 교통: 노선 신설보다 재원, 착공 시기, 관계기관 협의 여부
- 주거: 공급 물량보다 대상, 위치, 인허가 단계
- 돌봄·복지: 지원 대상, 신청 방식, 기존 제도와의 차이
- 지역경제: 소상공인 지원, 관광, 산업단지, 청년 일자리
- 안전·환경: 침수, 폭염, 하천, 공원, 재난 대응 체계

## 주민 입장에서 중요한 질문

| 질문 | 왜 중요한가 |
| --- | --- |
| 임기 안에 시작 가능한가 | 장기 계획과 단기 실행 과제를 구분할 수 있습니다 |
| 예산 출처가 적혀 있는가 | 국비, 시도비, 자체 예산에 따라 실행 가능성이 달라집니다 |
| 기존 사업과 겹치지 않는가 | 새 공약인지 기존 사업의 연장인지 확인할 수 있습니다 |
| 어느 지역이 먼저 혜택을 받는가 | 생활권별 체감 차이를 볼 수 있습니다 |

## 선거 결과와 공약을 함께 보는 법

{topic.keyword}을 검색할 때는 결과 숫자만 보지 말고, 당선인이 선거 기간에 내놓은 공약이 이후 행정 계획으로 어떻게 바뀌는지 봐야 합니다. 선거 공약은 약속이고, 예산안·업무계획·조례안은 실행 단계에 가까운 자료입니다.

특히 {region} 지역처럼 생활권이 넓거나 현안이 많은 곳은 하나의 대표 공약만으로 판단하기 어렵습니다. 교통 공약은 광역 계획과 연결되는지, 복지 공약은 기존 중앙정부 제도와 중복되지 않는지, 개발 공약은 환경·주민 의견 절차가 남아 있는지 따로 확인하는 편이 좋습니다.

## 바로 확인할 링크

- [중앙선거관리위원회 정책공약마당](https://policy.nec.go.kr/)
- [중앙선거관리위원회 선거통계시스템](https://info.nec.go.kr/)
- [중앙선거관리위원회 선거자료공개포털](https://data.nec.go.kr/)

공식 통계가 갱신된 뒤에는 {topic.keyword}의 당선인명, 득표율, 주요 공약을 한 번 더 대조해 보는 것이 좋습니다. 블로그 글은 빠르게 흐름을 잡는 용도로 보고, 최종 확인은 중앙선관위와 지자체 공식 자료를 기준으로 삼으면 안전합니다.
"""
    return Draft(
        topic=topic,
        title=title,
        slug=make_slug(topic.keyword),
        excerpt=f"{topic.keyword}을 공식 선거자료와 지역 현안 기준으로 확인하는 방법입니다.",
        body_markdown=body,
        tags=[
            topic.category,
            "지방선거",
            "당선인공약",
            "선거결과",
            region,
        ],
    )


def title_for(keyword: str, index: int) -> str:
    suffixes = [
        "5가지만 먼저 보기",
        "공식자료 확인 순서",
        "주민이 볼 핵심 기준",
        "공약 읽는 법",
        "선거 결과와 함께 보기",
    ]
    return f"{keyword}, {suffixes[index % len(suffixes)]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--min-quality", type=float, default=60)
    parser.add_argument("--llm-edit", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    settings.publisher = "markdown"
    if not args.llm_edit:
        settings.enable_llm_edit = False
    editor = SeoEditorAgent(settings)
    images = ImageAgent(settings)
    publisher = MarkdownPublisher(settings.output_dir)

    topics = build_topics(args.count, settings)
    print(f"{len(topics)} election topics selected")
    published: list[str] = []
    start = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=5)

    for index, topic in enumerate(topics):
        draft = build_draft(topic, index)
        draft = editor.improve(draft)
        draft = images.attach_cover(draft)
        draft.created_at = start - timedelta(minutes=index * 13)
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
    print(f"\npublished {len(published)} election posts")


if __name__ == "__main__":
    main()
