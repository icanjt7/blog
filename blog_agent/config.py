from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel


class Settings(BaseModel):
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    output_dir: Path = Path("output/posts")
    state_dir: Path = Path("state")
    publisher: str = "markdown"
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_app_password: str | None = None


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        output_dir=Path(os.getenv("BLOG_OUTPUT_DIR", "output/posts")),
        state_dir=Path(os.getenv("BLOG_STATE_DIR", "state")),
        publisher=os.getenv("PUBLISHER", "markdown"),
        wordpress_url=os.getenv("WORDPRESS_URL") or None,
        wordpress_username=os.getenv("WORDPRESS_USERNAME") or None,
        wordpress_app_password=os.getenv("WORDPRESS_APP_PASSWORD") or None,
    )
