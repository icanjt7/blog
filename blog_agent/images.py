from __future__ import annotations

import base64
import urllib.parse
from pathlib import Path

import requests
from openai import OpenAI

from .config import Settings
from .models import Draft


class ImageAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.assets_dir = settings.assets_dir
        self._openai: OpenAI | None = (
            OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        )

    def attach_cover(self, draft: Draft) -> Draft:
        draft.image_prompt = self.build_prompt(draft)
        draft.cover_image_alt = f"{draft.title} 대표 이미지"

        # 1. Unsplash free API (key required, 50 req/h)
        if self.settings.unsplash_access_key:
            url = self._fetch_unsplash(draft)
            if url:
                draft.cover_image_path = url
                return draft

        # 2. OpenAI image generation (paid, opt-in)
        if self.settings.enable_image_generation and self._openai:
            local_path = self._generate_openai(draft)
            if local_path:
                draft.cover_image_path = local_path
                return draft

        # 3. Picsum Photos — free, no key, keyword-seeded for consistency
        draft.cover_image_path = self._picsum_url(draft)
        return draft

    def _fetch_unsplash(self, draft: Draft) -> str | None:
        keyword = f"{draft.topic.keyword} {draft.topic.category}"
        query = urllib.parse.quote(keyword)
        try:
            resp = requests.get(
                "https://api.unsplash.com/search/photos",
                params={"query": query, "per_page": 3, "orientation": "landscape"},
                headers={"Authorization": f"Client-ID {self.settings.unsplash_access_key}"},
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                photo = results[0]
                # utm params required by Unsplash API guidelines
                url = photo["urls"]["regular"]
                src_url = photo["links"]["html"]
                author = photo["user"]["name"]
                # store attribution in alt text
                draft.cover_image_alt = (
                    f"{draft.title} — Photo by {author} on Unsplash ({src_url})"
                )
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
    def _picsum_url(draft: Draft) -> str:
        import hashlib
        seed = int(hashlib.md5(draft.slug.encode()).hexdigest()[:8], 16) % 1000
        return f"https://picsum.photos/seed/{seed}/1200/630"

    @staticmethod
    def build_prompt(draft: Draft) -> str:
        context = " ".join(draft.body_markdown.split())[:700]
        category_moods = {
            "living": "clear public-service editorial, helpful everyday information",
            "tech": "modern tech magazine cover, clean devices and abstract interface elements",
            "finance": "trustworthy financial briefing, charts and documents without readable numbers",
            "local": "curated local guide mood, maps and city details without logos",
        }
        mood = category_moods.get(draft.topic.category, "clean editorial news briefing")
        return (
            "Create a 16:9 editorial cover image for a Korean news-style information channel. "
            f"Article title/theme: {draft.title}. "
            f"Keyword: {draft.topic.keyword}. "
            f"Context: {context}. "
            f"Visual mood: {mood}. "
            "No readable text, no brand logos, no fake UI, no people implying firsthand review. "
            "Use a polished, credible, news briefing style suitable for a blog thumbnail."
        )
