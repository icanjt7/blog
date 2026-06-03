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

POPULAR_TOPICS["생활"].extend([
    ("무더위 숙면 방법", "열대야에 잠을 덜 설치기 위한 실내 환경과 습관"),
    ("장마철 빨래 냄새 제거", "실내 건조와 세탁조 관리 포인트"),
    ("여름 피부 진정 루틴", "자외선과 땀으로 예민해진 피부 관리"),
    ("냉방병 예방 습관", "실내외 온도차와 수분 섭취 기준"),
    ("휴가 전 집 점검 리스트", "전기, 수도, 택배, 보안 체크"),
    ("여름철 차량 관리", "타이어, 에어컨 필터, 냉각수 확인"),
    ("전기차 충전요금 아끼는 법", "충전 시간대와 카드 혜택 확인"),
    ("청소기 필터 관리법", "흡입력 저하를 막는 교체와 세척 기준"),
    ("에어프라이어 청소법", "기름때와 냄새를 줄이는 관리 순서"),
    ("커피값 줄이는 습관", "구독, 캡슐, 텀블러 혜택 비교"),
    ("식비 절약 장보기 루틴", "일주일 식단과 냉장고 재고 관리"),
    ("편의점 할인 조합", "통신사·페이·행사상품을 함께 보는 법"),
    ("카드 포인트 현금화", "소멸 전 확인해야 할 포인트 사용처"),
    ("교통비 아끼는 방법", "정기권, 환승, 알뜰교통 혜택 확인"),
    ("월세 관리비 아끼는 법", "공과금과 관리비 고지서 체크"),
    ("분리수거 헷갈리는 품목", "플라스틱, 비닐, 종이류 구분 기준"),
    ("집안 냄새 제거 방법", "배수구, 신발장, 냉장고 냄새 관리"),
    ("수건 냄새 없애는 세탁법", "세제량과 건조 습관 점검"),
    ("여름 도시락 보관법", "식중독을 줄이는 준비와 보관 기준"),
    ("모기 덜 물리는 생활 팁", "방충망, 물 고임, 외출복 관리"),
    ("공과금 자동이체 혜택", "카드와 은행별 할인 확인"),
    ("가계부 쉽게 쓰는 법", "고정비와 변동비를 나누는 방법"),
    ("구독 서비스 정리 방법", "자동결제 새는 돈을 찾는 순서"),
    ("이사 전 체크리스트", "주소 이전, 공과금, 보증금 확인"),
    ("원룸 습기 관리", "환기와 제습 도구 선택 기준"),
    ("아이 방 여름 온도 관리", "수면과 냉방 온도를 함께 보는 기준"),
    ("캠핑 준비물 체크리스트", "초보 캠핑 전 챙겨야 할 물품"),
    ("비 오는 날 신발 관리", "젖은 신발 냄새와 변형 방지"),
    ("여름 생수 고르는 법", "보관과 음용량, 외출용 선택 기준"),
    ("홈트 초보 루틴", "매일 10분 운동을 이어가는 방법"),
    ("아침 루틴 만드는 법", "출근 전 시간을 덜 허둥대는 순서"),
    ("냉동식품 보관 기준", "유통기한과 냉동실 정리 방법"),
    ("전자레인지 청소법", "냄새와 얼룩을 줄이는 생활 팁"),
    ("여름 침구 관리", "땀과 습기를 줄이는 세탁 주기"),
    ("여행자보험 고르는 법", "국내외 여행 전 보장 항목 확인"),
    ("공항 수하물 줄이는 법", "기내 반입과 위탁 수하물 기준"),
    ("비상약 준비 리스트", "여행과 여름철에 자주 쓰는 약 정리"),
    ("장보기 앱 비교 기준", "배송비, 신선도, 쿠폰을 함께 보는 법"),
    ("전기밥솥 관리법", "냄새와 보온 전기요금 줄이는 습관"),
    ("물때 제거 청소 루틴", "욕실과 주방을 나눠 관리하는 법"),
    ("선풍기 청소 방법", "먼지 제거와 안전한 분해 순서"),
    ("여름 향수 고르는 법", "습도와 체온에 맞는 향 선택"),
    ("반찬 오래 보관하는 법", "냉장·냉동 보관 기준"),
    ("가성비 단백질 식단", "계란, 두부, 닭가슴살 활용 기준"),
    ("택배 분실 대처법", "배송완료 후 확인해야 할 절차"),
])

POPULAR_TOPICS["기술"].extend([
    ("맥북 배터리 관리", "충전 습관과 배터리 성능 상태 확인"),
    ("윈도우 노트북 느려졌을 때", "시작프로그램과 저장공간 점검"),
    ("스마트폰 사진 백업", "클라우드와 외장 저장장치 활용"),
    ("아이패드 필기 앱 비교", "강의, 회의, 독서 노트 용도별 선택"),
    ("갤럭시 사진 보정 팁", "기본 앱으로 색감과 구도를 다듬는 방법"),
    ("AI 회의록 도구 비교", "녹음, 요약, 개인정보 기준"),
    ("무료 AI 번역 도구", "문서와 이메일 번역에 맞는 선택"),
    ("블로그 썸네일 만드는 법", "AI 이미지와 무료 디자인 도구 활용"),
    ("스마트폰 저장공간 정리", "사진, 앱, 캐시를 줄이는 순서"),
    ("USB-C 케이블 고르는 법", "충전속도와 데이터 전송 규격 확인"),
    ("모니터 주사율 고르는 법", "업무, 영상, 게임 용도별 기준"),
    ("사무용 키보드 선택", "소음, 배열, 연결 방식을 비교"),
    ("기계식 키보드 입문", "축 종류와 소음 기준 정리"),
    ("웹캠 화질 좋아지는 법", "조명, 배경, 카메라 설정 팁"),
    ("재택근무 장비 추천 기준", "모니터, 의자, 마이크 우선순위"),
    ("VPN 사용 전 확인할 점", "보안, 속도, 개인정보 정책"),
    ("비밀번호 관리 앱 비교", "가족 공유와 2단계 인증 기준"),
    ("패스키란 무엇인가", "비밀번호 없는 로그인의 장단점"),
    ("스미싱 차단 앱 활용", "문자 링크와 악성 앱을 막는 방법"),
    ("공유기 보안 설정", "비밀번호, 펌웨어, 게스트망 관리"),
    ("스마트홈 입문", "조명, 플러그, 허브 선택 기준"),
    ("로봇청소기 고르는 법", "흡입력보다 중요한 센서와 관리"),
    ("무선충전기 고르는 법", "발열과 충전 규격 확인"),
    ("휴대용 모니터 선택", "노트북 보조 화면으로 보는 기준"),
    ("전자책 리더기 고르는 법", "눈 피로와 화면 크기 비교"),
    ("블루투스 스피커 선택", "실내외 용도와 배터리 기준"),
    ("게이밍 노트북 발열 관리", "소음과 성능 저하를 줄이는 방법"),
    ("중고 노트북 살 때 확인", "배터리, 액정, 포트 점검"),
    ("스마트폰 중고거래 체크", "IMEI, 배터리, 외관 확인"),
    ("개인정보 삭제 방법", "중고 기기 판매 전 초기화 순서"),
    ("사진 AI 보정 도구", "인물, 음식, 여행 사진 보정 기준"),
    ("영상 편집 앱 입문", "숏폼과 브이로그용 도구 선택"),
    ("마이크 고르는 법", "화상회의와 녹음용 기준"),
    ("노트북 거치대 효과", "자세와 발열을 함께 보는 기준"),
    ("SSD 용량 고르는 법", "작업용·게임용 저장공간 기준"),
    ("외장하드와 SSD 비교", "백업 목적별 선택 기준"),
    ("프린터 유지비 비교", "잉크젯과 레이저 비용 확인"),
    ("스마트폰 요금제와 기기값", "자급제와 약정 구매 비교"),
    ("AI 검색엔진 활용법", "검색 결과를 검증하는 질문법"),
    ("코딩 공부 AI 활용", "초보자가 막히는 부분을 물어보는 법"),
    ("크롬 확장프로그램 정리", "속도와 보안을 함께 관리"),
    ("노트북 화상회의 세팅", "카메라, 마이크, 조명 순서"),
    ("NAS 사진 백업 루틴", "가족 사진을 안전하게 보관하는 방법"),
    ("홈 와이파이 음영지역 해결", "메시 와이파이와 공유기 위치"),
])

POPULAR_TOPICS["핫이슈"].extend([
    ("서울 망원시장 먹거리", "시장 간식과 주변 산책 동선"),
    ("서울 북촌 한옥마을 코스", "사진 포인트와 조용한 동선"),
    ("서울 익선동 데이트 코스", "카페와 골목 산책을 묶는 방법"),
    ("서울 잠실 석촌호수 산책", "카페와 야경을 함께 보는 코스"),
    ("서울 홍대 합정 카페 동선", "주말 방문 전 혼잡도와 이동 순서"),
    ("부산 광안리 저녁 코스", "해변, 카페, 야경 포인트"),
    ("부산 흰여울문화마을 코스", "사진 포인트와 이동 동선"),
    ("부산 송정 바다 카페", "드라이브와 카페를 묶는 코스"),
    ("제주 서귀포 비 오는 날", "실내 관광지와 카페 동선"),
    ("제주 애월 카페거리", "해안도로와 카페 방문 순서"),
    ("제주 성산 일출봉 주변", "일출 후 함께 볼 만한 코스"),
    ("강릉 주문진 당일치기", "시장, 바다, 카페를 묶는 일정"),
    ("속초 대포항 먹거리", "해산물과 시장 방문 전 확인할 점"),
    ("양양 서핑 거리 코스", "해변과 카페를 함께 보는 방법"),
    ("경주 불국사 주변 코스", "유적지와 카페를 묶는 동선"),
    ("경주 보문단지 산책", "호수와 야경을 함께 보는 코스"),
    ("전주 객리단길 카페", "한옥마을 이후 이어가기 좋은 동선"),
    ("군산 근대거리 여행", "빵집과 사진 포인트를 함께 보는 코스"),
    ("여수 낭만포차 거리", "저녁 방문 전 알아둘 동선"),
    ("통영 동피랑 벽화마을", "시장과 전망 포인트를 묶는 코스"),
    ("남해 보리암 여행", "드라이브와 전망 포인트"),
    ("포항 스페이스워크 코스", "영일대와 함께 보는 동선"),
    ("대구 김광석거리 코스", "카페와 골목 산책을 묶는 방법"),
    ("대구 동성로 맛집 동선", "카페와 식사 코스 정리"),
    ("광주 양림동 펭귄마을", "골목 산책과 카페 방문 순서"),
    ("전남 담양 메타세쿼이아길", "죽녹원과 함께 보는 당일 코스"),
    ("순천만 국가정원 코스", "정원과 시장을 묶는 일정"),
    ("대전 장태산 자연휴양림", "숲길과 카페를 함께 보는 코스"),
    ("청주 수암골 카페거리", "전망과 골목 산책 코스"),
    ("수원 행궁동 카페거리", "화성과 함께 걷는 동선"),
    ("용인 에버랜드 주변 코스", "방문 전후 함께 갈 만한 곳"),
    ("파주 헤이리마을 코스", "전시와 카페를 묶는 방법"),
    ("고양 스타필드 주변 코스", "쇼핑과 식사를 함께 보는 동선"),
    ("인천 송도 센트럴파크", "야경과 산책 코스"),
    ("인천 월미도 당일치기", "바다와 먹거리를 묶는 동선"),
    ("가평 남이섬 당일치기", "선착장과 주변 카페 동선"),
    ("춘천 소양강 스카이워크", "닭갈비와 함께 보는 코스"),
    ("원주 소금산 출렁다리", "산책과 주변 볼거리"),
    ("제천 청풍호반 케이블카", "전망과 드라이브 코스"),
    ("단양 도담삼봉 코스", "사진 포인트와 시장 동선"),
    ("안동 월영교 야경", "하회마을과 함께 보는 일정"),
    ("울산 대왕암공원 산책", "바다 산책과 카페 동선"),
    ("창원 마산어시장 먹거리", "시장 방문 전 알아둘 메뉴"),
    ("김해 봉리단길 카페", "가볍게 걷기 좋은 동선"),
])

TITLE_OVERRIDES = {
    "생활": ("놓치기 쉬운", "아끼는", "먼저 볼", "바로 써먹는", "헷갈릴 때 보는"),
    "기술": ("고르기 전 볼", "초보가 먼저 볼", "체감 기준", "설정부터 바꾸는", "실패 줄이는"),
    "핫이슈": ("처음 가면 이 동선", "하루 코스로 묶기", "비 오면 이 코스", "저녁에 걷기 좋은", "먹거리 동선"),
}


def fallback_title(keyword: str, category: str, index: int) -> str:
    styles = TITLE_OVERRIDES.get(category, ("먼저 볼",))
    style = styles[index % len(styles)]
    if category == "핫이슈":
        return f"{keyword}, {style}"
    if style.endswith("는"):
        return f"{keyword} {style} 법"
    return f"{keyword}: {style} 기준"


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
        if "핵심 정리" in draft.title or "지금 확인할 포인트" in draft.title:
            draft.title = fallback_title(topic.keyword, topic.category, index)
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
