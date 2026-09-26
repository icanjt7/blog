from __future__ import annotations

import argparse
import json
from pathlib import Path


GENRES = (("드라마", "drama"), ("미스터리", "mystery"), ("코미디", "comedy"), ("다큐멘터리", "documentary"), ("SF", "science-fiction"))


def fixture(index: int) -> dict:
    genre, genre_slug = GENRES[(index - 1) % len(GENRES)]
    title = f"넷플릭스 파이프라인 검증작 {index:02d}"
    return {
        "post_type": "ENTERTAINMENT_NETFLIX",
        "id": f"netflix-canary-{index:03d}",
        "content_type": "tv" if index % 2 else "movie",
        "title": title,
        "slug": f"netflix-pipeline-canary-{index:03d}",
        "genre": genre,
        "genre_slug": genre_slug,
        "year": 2026,
        "summary_box": {
            "genre_rating": f"{genre} · 12세 이상 관람가",
            "episodes_runtime": "8부작 · 회당 50분" if index % 2 else "영화 · 110분",
            "casting_direction": f"테스트 배우 {index} · 스테이징 연출 {index}",
        },
        "director": f"스테이징 연출 {index}",
        "cast": [f"테스트 배우 {index}", f"테스트 배우 {index + 50}"],
        "synopsis": f"{title}은 대용량 정적 빌드와 시맨틱 템플릿을 검증하기 위한 가상 콘텐츠입니다. 실제 넷플릭스 작품이 아닙니다.",
        "characters": [
            {"name": f"검증 인물 {index}", "relationship": "서로 다른 목표를 조율하며 사건을 이끄는 가상 인물"},
            {"name": f"검증 인물 {index + 50}", "relationship": "주인공의 선택을 점검하는 가상 협력자"},
        ],
        "viewing_points": [
            "장면 전환과 반응형 이미지가 안정적으로 표시되는지 확인할 수 있습니다.",
            "네 단계 제목 구조와 등장인물 목록의 접근성을 검증합니다.",
            "병렬 렌더링에서도 토스 상품 카드가 누락되지 않는지 확인합니다.",
        ],
        "ending_analysis": "가상 검증 데이터의 마지막에는 모든 테스트 항목이 완료됩니다. 실제 작품의 결말이나 후속 시즌 정보가 아닙니다.",
        "youtube_key": "M7lc1UVf-VE",
        "rating": 4.5,
        "reviews": [
            "화면 구성과 장면 전환이 안정적이라 모바일에서도 내용을 따라가기 편했습니다.",
            "관전 포인트와 스포일러 구분이 명확해 원하는 정보만 골라 읽기 좋았습니다.",
            "예고편과 작품 정보가 한 페이지에 있어 시청 여부를 판단하기 수월했습니다.",
        ],
        "review_summary": {
            "strengths": ["페이지 구조가 읽기 쉽다는 테스트 의견", "포스터 비율이 안정적이라는 테스트 의견", "스포일러 토글이 명확하다는 테스트 의견"],
            "weaknesses": ["가상 데이터라 실제 작품 정보가 없다는 점", "성능 검증 목적이라 서사가 단순하다는 점"],
        },
        "poster_url": "https://briefwave.kr/assets/movies/3ecc7a31231d-staging-cinema-poster.webp",
        "poster_alt": f"{title}용 추상 영화관 QA 포스터",
        "source_url": "https://briefwave.kr/about.html",
        "reviews_source_url": "https://briefwave.kr/editorial-policy.html",
        "updated_at": "2026-09-24T00:00:00+09:00",
        "is_fixture": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--count", type=int, default=50)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index in range(1, args.count + 1):
            handle.write(json.dumps(fixture(index), ensure_ascii=False, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
