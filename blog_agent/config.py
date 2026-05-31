from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_image_model: str = "gpt-image-1-mini"
    post_count: int = 5
    enable_llm_edit: bool = True
    enable_image_generation: bool = False
    output_dir: Path = Path("output/posts")
    assets_dir: Path = Path("output/assets")
    public_dir: Path = Path("public")
    state_dir: Path = Path("state")
    site_title: str = "브리핑웨이브"
    custom_domain: str | None = None
    publisher: str = "markdown"
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_app_password: str | None = None
    wordpress_status: str = "publish"


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini"),
        post_count=int(os.getenv("BLOG_POST_COUNT", "5")),
        enable_llm_edit=os.getenv("ENABLE_LLM_EDIT", "true").lower() == "true",
        enable_image_generation=os.getenv("ENABLE_IMAGE_GENERATION", "false").lower() == "true",
        output_dir=Path(os.getenv("BLOG_OUTPUT_DIR", "output/posts")),
        assets_dir=Path(os.getenv("BLOG_ASSETS_DIR", "output/assets")),
        public_dir=Path(os.getenv("BLOG_PUBLIC_DIR", "public")),
        state_dir=Path(os.getenv("BLOG_STATE_DIR", "state")),
        site_title=os.getenv("BLOG_SITE_TITLE", "브리핑웨이브"),
        custom_domain=os.getenv("BLOG_CUSTOM_DOMAIN") or None,
        publisher=os.getenv("PUBLISHER", "markdown"),
        wordpress_url=os.getenv("WORDPRESS_URL") or None,
        wordpress_username=os.getenv("WORDPRESS_USERNAME") or None,
        wordpress_app_password=os.getenv("WORDPRESS_APP_PASSWORD") or None,
        wordpress_status=os.getenv("WORDPRESS_STATUS", "publish"),
    )
