from __future__ import annotations

import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import feedparser
import requests
import yaml

from .models import Source, Topic


STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "for",
    "this",
    "that",
    "are",
    "is",
    "was",
    "were",
    "to",
    "of",
    "on",
    "in",
    "as",
    "by",
    "ordered",
    "built",
    "host",
    "disabling",
    "next",
    "month",
    "free",
    "how",
    "humans",
    "react",
    "surprises",
    "road",
    "congress",
    "just",
    "gave",
    "tried",
    "actually",
    "works",
    "정부",
    "발표",
    "지원",
    "관련",
    "안내",
    "단호히",
    "성과",
    "가능",
    "대응",
    "써도",
    "하반기",
    "확대",
    "시행",
    "올",
}

CATEGORY_SEEDS = {
    "생활": ["지원금", "청년", "신청방법", "제철음식", "생활비", "혜택"],
    "기술": ["AI", "아이폰", "갤럭시", "노트북", "스펙", "비교"],
    "정책": ["금리", "환율", "부동산", "대출", "연금", "세금"],
    "정치": ["지방선거", "당선인 공약", "선거 결과", "국회", "정당"],
    "스포츠": [
        "2026 월드컵 48개국 일정",
        "한국 축구 대표팀 월드컵 일정",
        "2026 월드컵 조별리그 관전법",
    ],
    "핫이슈": [
        "서울 맛집",
        "부산 여행",
        "제주 카페",
        "강릉 여행",
        "전주 맛집",
        "서울 성수 카페 동선",
        "부산 해운대 여행 코스",
        "제주 반려동물 동반여행",
        "서울 의료관광 병원",
        "경주 당일치기 코스",
        "여수 밤바다 여행",
        "전주 한옥마을 먹거리 동선",
    ],
}

BACKFILL_SEEDS = {
    "생활": [
        ("여름 전기요금 절약", "에어컨·제습기 같이 쓸 때 전기요금 줄이는 순서", "냉방 온도, 제습기 동시 사용, 대기전력, 전기요금 누진 구간을 생활비 관점에서 비교한다."),
        ("장마철 실내 습도 관리", "곰팡이 생기기 전 실내 습도 잡는 5가지 기준", "장마철 환기 시간, 제습기 위치, 욕실·베란다 곰팡이, 의류 보관을 중심으로 정리한다."),
        ("아이 방학 체험 예약", "방학 체험 예약 전에 확인할 연령·환불·동선 기준", "어린이 체험 프로그램의 연령 제한, 보호자 동반, 환불 마감, 이동 시간을 점검한다."),
        ("모바일 신분증 사용처", "모바일 신분증, 되는 곳과 안 되는 곳 구분법", "모바일 신분증과 실물 신분증 요구 상황, 금융·공공·민간 창구 차이를 설명한다."),
        ("여름철 식중독 예방", "냉장고에 넣어도 위험한 여름 음식 보관 기준", "조리 후 보관 시간, 도시락, 배달 음식, 재가열 기준을 생활 정보로 정리한다."),
        ("청년 월세 지원 확인", "청년 월세 지원, 소득·거주 조건 먼저 보는 법", "청년 주거 지원에서 연령, 소득, 임대차 계약, 중복 지원 여부를 점검한다."),
    ],
    "기술": [
        ("AI 노트북 NPU", "AI 노트북 살 때 NPU 숫자보다 먼저 볼 것", "AI PC의 NPU TOPS, 메모리, 배터리, 온디바이스 AI 기능, 실제 구매 판단 기준을 설명한다."),
        ("스마트폰 배터리 수명", "스마트폰 배터리 오래 쓰려면 바꿀 설정 6가지", "충전 습관, 발열, 백그라운드 앱, 화면 밝기, 고속 충전 사용 조건을 다룬다."),
        ("와이파이 7 공유기", "와이파이 7 공유기, 지금 바꿔도 되는 집은 따로 있다", "Wi-Fi 6E와 7의 차이, 6GHz 대역, 단말 호환, 집 구조, 백홀 구성을 설명한다."),
        ("클라우드 백업 비용", "사진 백업비 아끼려면 클라우드 구조부터 봐야 한다", "iCloud, Google Photos, OneDrive의 저장 용량, 가족 공유, 원본 보관, 중복 백업을 비교한다."),
        ("생성 AI 업무 자동화", "업무 자동화에 AI 붙이기 전 정해야 할 4가지", "반복 문서, 개인정보, 검수 책임, API 비용, 실패 시 수동 처리 기준을 설명한다."),
        ("패스키 로그인", "비밀번호 대신 패스키, 편하지만 먼저 확인할 것", "패스키의 기기 종속성, 복구 수단, 브라우저·OS 지원, 기업 계정 적용을 다룬다."),
    ],
    "정책": [
        ("전세대출 갈아타기", "전세대출 갈아타기 전 중도상환수수료부터 계산하기", "금리 차이, 중도상환수수료, 보증기관, 임대차 기간, DSR 영향을 비교한다."),
        ("청년도약계좌 유지", "청년도약계좌, 해지 전에 놓치기 쉬운 조건", "납입 기간, 정부 기여금, 소득 요건, 중도해지 사유, 만기 전략을 설명한다."),
        ("주택청약 통장 활용", "청약통장 오래 넣었는데 헷갈리는 가점 기준", "무주택 기간, 부양가족, 납입 인정액, 지역별 예치금 기준을 구분한다."),
        ("자동차세 연납", "자동차세 연납, 할인보다 먼저 봐야 할 일정", "신청 기간, 납부 월, 차량 매각·폐차 시 환급, 지방세 납부 경로를 정리한다."),
        ("소상공인 정책자금", "소상공인 정책자금 신청 전 준비할 서류와 순서", "업종 제한, 신용평가, 사업자등록, 매출 증빙, 온라인 접수 흐름을 설명한다."),
        ("건강보험 피부양자", "피부양자 탈락 기준, 소득과 재산을 따로 봐야 한다", "건강보험 피부양자 인정에서 소득, 재산, 사업자 등록, 가족관계를 구분한다."),
    ],
    "정치": [
        ("지방선거 공약 비교", "지방선거 공약, 후보 이름보다 예산부터 봐야 한다", "공약 비교에서 예산 근거, 권한 범위, 조례 필요 여부, 임기 내 실현 가능성을 설명한다."),
        ("선거구 확인 방법", "우리 동네 선거구 바뀌었는지 확인하는 법", "선거구 획정, 주소지 기준, 사전투표소, 후보자 등록 일정 확인 순서를 정리한다."),
        ("당선인 공약 점검", "당선인 공약, 취임 뒤 100일에 봐야 할 항목", "공약 이행 계획, 조직 개편, 예산 편성, 조례·법률 개정 필요성을 나눠 본다."),
        ("국회 법안 진행", "뉴스에 나온 법안, 통과된 건지 확인하는 순서", "발의, 상임위, 법사위, 본회의, 공포 단계의 차이를 설명한다."),
        ("정책 여론조사 읽기", "여론조사 볼 때 표본보다 먼저 봐야 할 숫자", "조사 기간, 표본 크기, 응답률, 표본오차, 질문 문구를 중립적으로 설명한다."),
        ("공공기관장 인사", "공공기관장 인사 뉴스, 임기와 권한부터 확인하기", "임명 절차, 임기, 주무부처, 기관 역할, 경영평가와의 관계를 정리한다."),
    ],
    "스포츠": [
        ("2026 월드컵 조편성", "2026 월드컵 조편성 전 알아둘 48개국 규칙", "48개국 확대, 조별리그, 32강 토너먼트, 3개국 공동 개최 변수를 설명한다."),
        ("한국 축구 대표팀 일정", "대표팀 경기 일정, 평가전과 예선 구분이 먼저다", "평가전, 예선, 본선, 소집 명단, 부상 변수와 한국 시간 확인법을 정리한다."),
        ("월드컵 티켓 예매", "월드컵 티켓 예매 전 공식 판매 단계 확인하기", "FIFA 공식 판매, 추첨·선착순 단계, 재판매, 숙박·이동 비용을 설명한다."),
        ("월드컵 개최 도시", "북중미 월드컵 개최 도시, 이동 거리가 변수다", "캐나다·미국·멕시코 개최 도시, 시차, 이동 거리, 휴식일 영향을 설명한다."),
        ("축구 대표팀 명단", "최종 명단 발표 전 예비 명단을 읽는 법", "예비 명단과 최종 명단, 부상 대체, 포지션 균형, 소속팀 출전 시간을 다룬다."),
        ("월드컵 중계 확인", "월드컵 중계 일정, 한국 시간으로 다시 봐야 하는 이유", "현지 시간, 한국 시간, 중계권, 하이라이트, 모바일 시청 조건을 설명한다."),
    ],
    "핫이슈": [
        ("아이와 실내 체험 여행", "비 오는 날 아이와 가기 좋은 실내 체험 코스", "박물관, 과학관, 키즈 체험, 예약 여부, 주차와 식사 동선을 비교한다."),
        ("가족 부산 여행 코스", "부산 가족여행, 해운대만 가면 아쉬운 동선", "해운대, 동백섬, 시장, 실내 대체 장소, 아이 동반 이동 거리를 고려한다."),
        ("제주 실내 관광지", "제주 비 오는 날, 실내 관광지만 묶는 동선", "제주 실내 전시, 카페, 체험 공간, 렌터카 이동, 우천 대안을 정리한다."),
        ("서울 성수 카페 동선", "성수 카페거리, 줄 서기 전에 동선부터 잡기", "성수역, 서울숲, 카페 대기, 편집숍, 식사 시간대를 중심으로 설명한다."),
        ("강릉 가족 여행", "강릉 가족여행, 바다와 실내 코스 같이 잡는 법", "경포, 주문진, 실내 전시, 카페, 주차와 식사 동선을 비교한다."),
        ("경주 당일치기 코스", "경주 당일치기, 유적지보다 쉬는 지점이 중요하다", "첨성대, 황리단길, 대릉원, 주차, 도보 이동, 가족 동선을 정리한다."),
    ],
}

_FALLBACK_URLS = {
    "생활": "https://www.korea.kr/",
    "기술": "https://developers.googleblog.com/",
    "정책": "https://www.fsc.go.kr/",
    "정치": "https://info.nec.go.kr/",
    "스포츠": "https://www.fifa.com/",
    "핫이슈": "https://korean.visitkorea.or.kr/",
}


class TrendScout:
    def __init__(self, state_dir: Path, source_file: Path | None = None) -> None:
        self.state_dir = state_dir
        self.source_file = source_file or Path(__file__).with_name("sources.yml")
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def scout(self, limit: int) -> list[Topic]:
        seen = self._load_seen_keywords()
        topics: list[Topic] = []
        topics.extend(self._topics_from_rss(seen))
        topics.extend(self._seed_topics(seen))
        ranked = sorted(
            topics,
            key=lambda item: (item.trend_score, -item.competition_score),
            reverse=True,
        )
        unique: list[Topic] = []
        used: set[str] = set()
        category_counts: Counter[str] = Counter()
        deferred: list[Topic] = []
        max_per_category = self._env_int("BLOG_MAX_PER_CATEGORY_PER_RUN", 1, minimum=1)
        strict_category_diversity = os.getenv("BLOG_STRICT_CATEGORY_DIVERSITY", "true").lower() == "true"
        for topic in ranked:
            key = self._topic_key(topic.keyword)
            if self._is_seen_topic(topic.keyword, used) or self._is_seen_topic(topic.keyword, seen):
                continue
            if category_counts[topic.category] >= max_per_category:
                deferred.append(topic)
                continue
            used.add(key)
            category_counts[topic.category] += 1
            unique.append(topic)
            if len(unique) >= limit:
                break
        if strict_category_diversity:
            return unique
        for topic in deferred:
            if len(unique) >= limit:
                break
            key = self._topic_key(topic.keyword)
            if self._is_seen_topic(topic.keyword, used) or self._is_seen_topic(topic.keyword, seen):
                continue
            used.add(key)
            unique.append(topic)
        return unique

    def remember(self, topics: list[Topic]) -> None:
        path = self.state_dir / "published_keywords.json"
        seen = self._load_seen_keywords()
        seen.update(self._topic_key(topic.keyword) for topic in topics)
        path.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2), encoding="utf-8")

    def _load_seen_keywords(self) -> set[str]:
        path = self.state_dir / "published_keywords.json"
        if not path.exists():
            return set()
        return {self._topic_key(keyword) for keyword in json.loads(path.read_text(encoding="utf-8"))}

    def _topics_from_rss(self, seen: set[str]) -> list[Topic]:
        config = yaml.safe_load(self.source_file.read_text(encoding="utf-8"))
        topics: list[Topic] = []
        for category, source_config in config.items():
            for rss_url in source_config.get("rss", []):
                try:
                    resp = requests.get(
                        rss_url,
                        headers={"User-Agent": "Mozilla/5.0 (compatible; blog-agent/1.0)"},
                        timeout=8,
                    )
                    resp.raise_for_status()
                    parsed = feedparser.parse(resp.content)
                except Exception:
                    continue
                for entry in parsed.entries[:10]:
                    title = re.sub(r"\s+", " ", entry.get("title", "")).strip()
                    if not title:
                        continue
                    if re.search(r"보도\s*(자료|참고)|참고자료", title):
                        continue
                    keyword = self._keyword_from_title(title)
                    if self._is_seen_topic(keyword, seen):
                        continue
                    published = self._published_at(entry)
                    recency = self._recency_score(published)
                    language_fit = 20 if re.search(r"[가-힣]", title) else -20
                    refined_category = self._refine_category(category, title, rss_url)
                    topics.append(
                        Topic(
                            keyword=keyword,
                            title_hint=title,
                            category=refined_category,
                            trend_score=55 + recency + language_fit,
                            competition_score=0.35,
                            rationale="RSS 신규성과 공식/전문 매체 출처 기반",
                            sources=[
                                Source(
                                    title=title,
                                    url=entry.get("link", rss_url),
                                    published_at=published,
                                    summary=entry.get("summary", ""),
                                    authority=4 if "korea.kr" in rss_url or ".go.kr" in rss_url else 3,
                                )
                            ],
                        )
                    )
        return topics

    def _seed_topics(self, seen: set[str]) -> list[Topic]:
        month = datetime.now().strftime("%m월")
        counter = Counter()
        for category, seeds in CATEGORY_SEEDS.items():
            if category == "스포츠" and os.getenv("ENABLE_SPORTS_SEEDS", "false").lower() != "true":
                continue
            for seed in seeds:
                keyword = seed if category == "스포츠" else f"{month} {seed}"
                counter[(category, keyword)] += 1
        topics = [
            Topic(
                keyword=keyword,
                title_hint=f"{keyword} 핵심 정리",
                category=category,
                trend_score=95 + score,
                competition_score=0.45,
                rationale="월별 반복 검색 수요가 있는 evergreen 키워드",
            )
            for (category, keyword), score in counter.items()
            if not self._is_seen_topic(keyword, seen)
        ]
        topics.extend(self._backfill_seed_topics(seen))
        return topics

    def _backfill_seed_topics(self, seen: set[str]) -> list[Topic]:
        month = datetime.now().strftime("%m월")
        topics: list[Topic] = []
        for category, seeds in BACKFILL_SEEDS.items():
            if category == "스포츠" and os.getenv("ENABLE_SPORTS_SEEDS", "false").lower() != "true":
                continue
            for index, (keyword, title_hint, summary) in enumerate(seeds):
                dated_keyword = f"{month} {keyword}"
                if self._is_seen_topic(dated_keyword, seen):
                    continue
                topics.append(
                    Topic(
                        keyword=dated_keyword,
                        title_hint=title_hint,
                        category=category,
                        trend_score=82 - index,
                        competition_score=0.35,
                        rationale="예약 발행 안정성을 위한 카테고리별 검색형 보강 주제",
                        sources=[
                            Source(
                                title=title_hint,
                                url=_FALLBACK_URLS.get(category, "https://www.korea.kr/"),
                                summary=summary,
                                authority=4,
                            )
                        ],
                    )
                )
        return topics

    @staticmethod
    def _keyword_from_title(title: str) -> str:
        quoted_terms = [
            re.sub(r"\s+", " ", term).strip(" '\"‘’“”")
            for term in re.findall(r"['‘’“\"]([^'‘’“\"]{2,})['‘’“\"]", title)
        ]
        quoted_terms = [
            term
            for term in quoted_terms
            if re.search(r"[가-힣A-Za-z0-9]", term) and not re.search(r"자료제공|문의", term)
        ]
        korean_tokens = re.findall(r"[가-힣]{2,}", title)
        if korean_tokens:
            filtered = [TrendScout._normalize_korean_token(token) for token in korean_tokens]
            filtered = [token for token in filtered if token and token not in STOPWORDS]
            if quoted_terms:
                quoted = TrendScout._normalize_korean_token(quoted_terms[0])
                rest = [token for token in filtered if token not in quoted]
                return " ".join([quoted, *rest[:3]]).strip() or title[:30]
            return " ".join(filtered[:4]) or title[:30]
        tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", title)
        filtered = [token for token in tokens if token.lower() not in STOPWORDS]
        if not filtered:
            return title[:30]
        preferred = [
            token
            for token in filtered
            if re.search(r"[A-Z0-9]", token) or token.lower() in {"ai", "mac", "ios"}
        ]
        keyword_tokens = preferred[:4] if len(preferred) >= 2 else filtered[:4]
        return " ".join(keyword_tokens)

    @staticmethod
    def _normalize_korean_token(token: str) -> str:
        if len(token) >= 3 and token[-1] in "이가은는을를":
            return token[:-1]
        return token

    @classmethod
    def _topic_key(cls, value: str) -> str:
        tokens = re.findall(r"[가-힣A-Za-z0-9]{2,}", value.lower())
        normalized = [
            cls._normalize_korean_token(token)
            for token in tokens
            if token and token not in STOPWORDS
        ]
        return " ".join(normalized) or value.lower().strip()

    @classmethod
    def _is_seen_topic(cls, value: str, seen: set[str]) -> bool:
        key = cls._topic_key(value)
        if key in seen:
            return True
        tokens = set(key.split())
        if len(tokens) < 3:
            return False
        for prior in seen:
            prior_tokens = set(prior.split())
            if len(prior_tokens) < 3:
                continue
            overlap = tokens & prior_tokens
            if len(overlap) >= 3 and len(overlap) / min(len(tokens), len(prior_tokens)) >= 0.75:
                return True
        return False

    @staticmethod
    def _refine_category(category: str, title: str, rss_url: str) -> str:
        text = f"{title} {rss_url}"
        if re.search(r"이재명정부|대통령|국무총리|외교|국회|정당|선거|투표|공약", text):
            return "정치"
        if re.search(r"AI|인공지능|로봇|스마트건설|반도체|소프트웨어|클라우드|데이터|디지털|모빌리티", text, re.IGNORECASE):
            return "기술"
        if re.search(r"국세청|탈세|체납|세금|금융|예금|금리|대출|부동산|재정|경제|공정위|관세|고용여건|고용동향|취업자|부총리|전 부처|물가|원자재", text):
            return "정책"
        if re.search(r"월드컵|축구|야구|농구|경기|대표팀|선수|리그", text):
            return "스포츠"
        if re.search(r"여권|신분증|신청|복지|건강|안전|청년|가족|주거|교육", text):
            return "생활"
        return category

    @staticmethod
    def _published_at(entry: dict) -> datetime | None:
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if not parsed:
            return None
        return datetime(*parsed[:6])

    @staticmethod
    def _recency_score(published_at: datetime | None) -> float:
        if not published_at:
            return 5
        age = datetime.now() - published_at
        if age < timedelta(days=1):
            return 30
        if age < timedelta(days=3):
            return 20
        if age < timedelta(days=7):
            return 10
        return 3

    @staticmethod
    def _env_int(name: str, default: int, minimum: int = 0) -> int:
        try:
            return max(minimum, int(os.getenv(name, str(default))))
        except ValueError:
            return max(minimum, default)
