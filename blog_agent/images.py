from __future__ import annotations

import base64
import hashlib
import urllib.parse
from pathlib import Path

import requests
from openai import OpenAI

from .config import Settings
from .models import Draft


VISUAL_KEYWORDS: tuple[tuple[str, str], ...] = (
    # 생활/지역
    ("맛집", "korean restaurant food table dining"),
    ("카페", "coffee cafe interior dessert"),
    ("여행", "travel destination landmark walking"),
    ("관광", "tourism destination travel"),
    ("제주", "jeju island coastline cafe"),
    ("부산", "busan haeundae beach skyline ocean"),
    ("강릉", "gangneung beach coffee street travel"),
    ("서울", "seoul restaurant street city food"),
    ("전주", "jeonju hanok village korean food"),
    # 기술
    ("아이폰", "smartphone technology"),
    ("갤럭시", "smartphone technology"),
    ("노트북", "laptop desk technology"),
    ("스펙", "technology device closeup"),
    ("비교", "technology comparison desk"),
    ("AI", "artificial intelligence circuit"),
    ("인공지능", "artificial intelligence circuit"),
    ("디지털", "digital technology abstract"),
    ("반도체", "semiconductor chip circuit"),
    ("우주", "space astronomy science"),
    ("과학", "science research laboratory"),
    ("양자", "quantum science abstract"),
    ("소프트웨어", "software code screen"),
    ("통신", "network communication infrastructure"),
    # 정책/경제
    ("지원금", "public service documents"),
    ("청년", "young professionals city"),
    ("생활비", "household budget notebook"),
    ("혜택", "public service checklist"),
    ("신청", "application form document"),
    ("제철음식", "seasonal korean food"),
    ("금리", "financial chart desk"),
    ("환율", "currency exchange finance"),
    ("대출", "loan documents finance"),
    ("부동산", "real estate apartment city"),
    ("연금", "retirement finance documents"),
    ("세금", "tax document calculator"),
    ("물가", "economy price market statistics"),
    ("예산", "government budget finance"),
    ("수출", "global trade export shipping"),
    ("무역", "trade port shipping container"),
    ("투자", "investment finance growth"),
    # 문화/유산
    ("유산", "korean heritage architecture"),
    ("문화재", "korean heritage traditional"),
    ("공연", "performance stage arts"),
    ("전시", "exhibition gallery art"),
    ("문화", "culture arts creative"),
    ("관람", "museum exhibition visitors"),
    # 사회/행정
    ("선거", "election civic government"),
    ("공무원", "government office building"),
    ("행정", "administration office paperwork"),
    ("안전", "safety public service"),
    ("재해", "disaster response emergency"),
    ("복구", "recovery construction work"),
    # 외교/국제
    ("외교", "diplomacy international summit"),
    ("OECD", "international conference summit"),
    ("유네스코", "heritage international organization"),
    ("정상", "government meeting official"),
    ("회의", "conference meeting table"),
    # 의료/교육/환경
    ("의료", "healthcare medical clean"),
    ("교육", "education classroom books"),
    ("기후", "climate environment green"),
    ("환경", "environment nature green"),
)

CATEGORY_VISUALS = {
    "핫이슈": "korean city news editorial",
    "기술": "modern technology editorial",
    "정책": "finance policy documents",
    "생활": "everyday lifestyle public information",
    "local": "local travel guide editorial",
    "tech": "modern technology editorial",
    "finance": "finance policy documents",
    "living": "everyday lifestyle public information",
}


class ImageAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.assets_dir = settings.assets_dir
        self._openai: OpenAI | None = (
            OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        )

    def attach_cover(self, draft: Draft) -> Draft:
        draft.image_prompt = self.build_prompt(draft)
        draft.cover_image_alt = f"{draft.topic.keyword} 관련 대표 이미지"

        # 1~3: 무료 스톡 API (설정된 첫 번째 키 사용)
        for fetch_fn in (self._fetch_unsplash, self._fetch_pexels, self._fetch_pixabay):
            url = fetch_fn(draft)
            if url:
                draft.cover_image_path = url
                return draft

        # 4. OpenAI image generation (paid, opt-in)
        if self.settings.enable_image_generation and self._openai:
            local_path = self._generate_openai(draft)
            if local_path:
                draft.cover_image_path = local_path
                return draft

        # 5. keyword-seeded picsum fallback
        draft.cover_image_path = self._fallback_url(draft)
        return draft

    def _fetch_unsplash(self, draft: Draft) -> str | None:
        if not self.settings.unsplash_access_key:
            return None
        query = self.visual_query(draft.topic.keyword, draft.topic.category, draft.title)
        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 10,
                        "orientation": "landscape", "content_filter": "high"},
                headers={"Authorization": f"Client-ID {self.settings.unsplash_access_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                # slug 해시로 결과 중 하나를 일관성 있게 선택
                idx = int(hashlib.md5(draft.slug.encode()).hexdigest()[:4], 16) % len(results)
                photo = results[idx]
                url = photo["urls"].get("regular") or photo["urls"].get("full")
                author = photo["user"]["name"]
                draft.cover_image_alt = f"{draft.title} — Photo by {author} on Unsplash"
                return url
        except Exception:
            pass
        return None

    def _fetch_pexels(self, draft: Draft) -> str | None:
        if not self.settings.pexels_api_key:
            return None
        query = self.visual_query(draft.topic.keyword, draft.topic.category, draft.title)
        try:
            resp = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": query, "per_page": 10, "orientation": "landscape"},
                headers={"Authorization": self.settings.pexels_api_key},
                timeout=10,
            )
            resp.raise_for_status()
            photos = resp.json().get("photos", [])
            if photos:
                idx = int(hashlib.md5(draft.slug.encode()).hexdigest()[:4], 16) % len(photos)
                photo = photos[idx]
                url = photo["src"].get("large2x") or photo["src"].get("large")
                draft.cover_image_alt = (
                    f"{draft.title} — Photo by {photo['photographer']} on Pexels"
                )
                return url
        except Exception:
            pass
        return None

    def _fetch_pixabay(self, draft: Draft) -> str | None:
        if not self.settings.pixabay_api_key:
            return None
        query = self.visual_query(draft.topic.keyword, draft.topic.category, draft.title)
        try:
            resp = requests.get(
                "https://pixabay.com/api/",
                params={
                    "key": self.settings.pixabay_api_key,
                    "q": query,
                    "image_type": "photo",
                    "orientation": "horizontal",
                    "per_page": 10,
                    "safesearch": "true",
                },
                timeout=10,
            )
            resp.raise_for_status()
            hits = resp.json().get("hits", [])
            if hits:
                idx = int(hashlib.md5(draft.slug.encode()).hexdigest()[:4], 16) % len(hits)
                photo = hits[idx]
                url = photo.get("largeImageURL") or photo.get("webformatURL")
                draft.cover_image_alt = f"{draft.title} — Photo via Pixabay"
                return url
        except Exception:
            pass
        return None

    def _generate_openai(self, draft: Draft) -> str | None:
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        image_path = self.assets_dir / f"{draft.slug}-cover.png"
        try:
            response = self._openai.images.generate(  # type: ignore[union-attr]
                model=self.settings.openai_image_model,
                prompt=draft.image_prompt or self.build_prompt(draft),
                size="1536x1024",
                quality="low",
                n=1,
            )
            image_b64 = response.data[0].b64_json
            image_path.write_bytes(base64.b64decode(image_b64))
            return str(image_path)
        except Exception:
            return None

    @staticmethod
    def _fallback_url(draft: Draft) -> str:
        seed = int(hashlib.md5(draft.slug.encode()).hexdigest()[:8], 16) % 1000
        return f"https://picsum.photos/seed/{seed}/1200/630"

    @staticmethod
    def visual_query(keyword: str, category: str, title: str = "") -> str:
        text = f"{keyword} {title}".lower()
        terms: list[str] = []
        for marker, visual in VISUAL_KEYWORDS:
            if marker.lower() in text:
                terms.append(visual)
        if not terms:
            terms.append(CATEGORY_VISUALS.get(category, "clean editorial news briefing"))
        return " ".join(dict.fromkeys(" ".join(terms).split()))

    @staticmethod
    def build_prompt(draft: Draft) -> str:
        context = " ".join(draft.body_markdown.split())[:700]
        category_moods = {
            "핫이슈": "curated Korean local news guide, city details, food or travel context when relevant",
            "기술": "modern tech magazine cover, clean devices and abstract interface elements",
            "정책": "trustworthy finance and policy briefing, charts and documents without readable numbers",
            "생활": "clear public-service editorial, helpful everyday information",
            "living": "clear public-service editorial, helpful everyday information",
            "tech": "modern tech magazine cover, clean devices and abstract interface elements",
            "finance": "trustworthy financial briefing, charts and documents without readable numbers",
            "local": "curated local guide mood, maps and city details without logos",
        }
        mood = category_moods.get(draft.topic.category, "clean editorial news briefing")
        visual_query = ImageAgent.visual_query(draft.topic.keyword, draft.topic.category, draft.title)
        return (
            "Create a 16:9 editorial cover image for a Korean news-style information channel. "
            f"Article title/theme: {draft.title}. "
            f"Keyword: {draft.topic.keyword}. "
            f"Concrete visual subject: {visual_query}. "
            f"Context: {context}. "
            f"Visual mood: {mood}. "
            "No readable text, no brand logos, no fake UI, no people implying firsthand review. "
            "Use a polished, credible, news briefing style suitable for a blog thumbnail."
        )
