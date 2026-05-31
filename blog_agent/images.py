from __future__ import annotations

import base64
from pathlib import Path

from openai import OpenAI

from .config import Settings
from .models import Draft


class ImageAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.assets_dir = settings.assets_dir

    def attach_cover(self, draft: Draft) -> Draft:
        prompt = self.build_prompt(draft)
        draft.image_prompt = prompt
        draft.cover_image_alt = f"{draft.title} 대표 이미지"
        if not self.settings.enable_image_generation or not self.client:
            return draft

        self.assets_dir.mkdir(parents=True, exist_ok=True)
        image_path = self.assets_dir / f"{draft.slug}-cover.png"
        response = self.client.images.generate(
            model=self.settings.openai_image_model,
            prompt=prompt,
            size="1536x1024",
            quality="low",
            n=1,
        )
        image_b64 = response.data[0].b64_json
        image_path.write_bytes(base64.b64decode(image_b64))
        draft.cover_image_path = str(image_path)
        return draft

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
