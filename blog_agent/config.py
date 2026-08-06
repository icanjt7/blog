from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel

from .trends import CATEGORY_SEEDS

# Canonical category order derived from CATEGORY_SEEDS so adding a seed
# automatically makes it a nav category.
_DEFAULT_CATEGORIES: list[str] = list(CATEGORY_SEEDS.keys())
DEFAULT_GA_MEASUREMENT_ID = "G-X7YV03FBW3"


class Settings(BaseModel):
    # LLM providers — tried in BLOG_LLM_PROVIDER_ORDER order.
    openai_api_key: str | None = None
    openai_model: str = "gpt-4.1-mini"
    openai_image_model: str = "gpt-image-1-mini"
    motif_api_key: str | None = None
    motif_model: str = "motif-12.7b-reasoning"
    motif_base_url: str = "https://chat.motiftech.io/openapi/v1"
    groq_api_key: str | None = None
    groq_model: str = "groq/compound"
    nvidia_api_key: str | None = None
    nvidia_model: str = "meta/llama-3.3-70b-instruct"
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    llm_timeout_seconds: float = 20
    github_token: str | None = None
    github_model: str = "openai/gpt-4.1"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    openrouter_api_key: str | None = None
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"

    # Images — free stock photo APIs (첫 번째 설정된 키 사용)
    unsplash_access_key: str | None = None   # 50 req/h free
    pexels_api_key: str | None = None        # 200 req/h free
    pixabay_api_key: str | None = None       # 100 req/min free
    tourapi_guide_key: str | None = None     # 한국관광공사 관광지별 연관 관광지 정보
    tourapi_rate_key: str | None = None      # 한국관광공사 관광지 집중률 방문자 추이 예측 정보
    tourapi_mdc_key: str | None = None       # 한국관광공사 의료관광 정보
    tourapi_pet_key: str | None = None       # 한국관광공사 반려동물 동반여행 정보
    tourapi_tour_key: str | None = None      # 한국관광공사 국문 관광정보 서비스
    tourapi_tour_en_key: str | None = None   # 한국관광공사 영문 관광정보 서비스
    tourapi_guide_endpoint: str = "https://apis.data.go.kr/B551011/TarRlteTarService1"
    tourapi_rate_endpoint: str = "https://apis.data.go.kr/B551011/TatsCnctrRateService"
    tourapi_mdc_endpoint: str = "https://apis.data.go.kr/B551011/KorService2"
    tourapi_pet_endpoint: str = "https://apis.data.go.kr/B551011/KorPetTourService2"
    tourapi_tour_endpoint: str = "https://apis.data.go.kr/B551011/KorService2"
    tourapi_tour_en_endpoint: str = "https://apis.data.go.kr/B551011/EngService2"
    tourapi_base_ym: str = "202503"

    # Analytics & monetisation
    ga_measurement_id: str | None = DEFAULT_GA_MEASUREMENT_ID    # Google Analytics 4: G-XXXXXXXXXX
    adsense_publisher_id: str | None = None  # AdSense: ca-pub-XXXXXXXXXX

    post_count: int = 5
    enable_llm_edit: bool = True
    enable_image_generation: bool = False
    output_dir: Path = Path("output/posts")
    assets_dir: Path = Path("output/assets")
    public_dir: Path = Path("public")
    state_dir: Path = Path("state")
    site_title: str = "브리핑웨이브"
    site_description: str = "브리핑웨이브에서 생활·기술·정책 소식을 쉽고 빠르게 확인하세요."
    custom_domain: str | None = None
    publisher: str = "both"
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_app_password: str | None = None
    wordpress_status: str = "publish"
    # Blogger configuration
    blogger_api_key: str | None = None
    blogger_blog_id: str | None = None
    # OAuth2 for Blogger (for publishing requires OAuth2 refresh token)
    blogger_oauth_client_id: str | None = None
    blogger_oauth_client_secret: str | None = None
    blogger_refresh_token: str | None = None
    # Top navigation categories — defaults to CATEGORY_SEEDS keys, so adding a
    # new seed automatically creates a nav category without extra config.
    categories: list[str] = _DEFAULT_CATEGORIES


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-1-mini"),
        motif_api_key=os.getenv("MOTIF_API") or os.getenv("MOTIF_API_KEY") or None,
        motif_model=os.getenv("MOTIF_MODEL", "motif-12.7b-reasoning"),
        motif_base_url=os.getenv("MOTIF_BASE_URL", "https://chat.motiftech.io/openapi/v1"),
        groq_api_key=os.getenv("GROQ_API_KEY") or None,
        groq_model=os.getenv("GROQ_MODEL", "groq/compound"),
        nvidia_api_key=os.getenv("NVIDIA_API_KEY") or os.getenv("LLAMA") or None,
        nvidia_model=os.getenv("NVIDIA_MODEL", "meta/llama-3.3-70b-instruct"),
        nvidia_base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "20")),
        github_token=os.getenv("GITHUB_TOKEN") or None,
        github_model=os.getenv("GITHUB_MODEL", "openai/gpt-4.1"),
        gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or None,
        openrouter_model=os.getenv("OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct:free"),
        unsplash_access_key=os.getenv("UNSPLASH_ACCESS_KEY") or None,
        pexels_api_key=os.getenv("PEXELS_API_KEY") or None,
        pixabay_api_key=os.getenv("PIXABAY_API_KEY") or None,
        tourapi_guide_key=os.getenv("TOURAPI_GUIDE") or None,
        tourapi_rate_key=os.getenv("TOURAPI_RATE") or None,
        tourapi_mdc_key=os.getenv("TOURAPI_MDC") or None,
        tourapi_pet_key=os.getenv("TOURAPI_PET") or None,
        tourapi_tour_key=os.getenv("TOURAPI_TOUR") or None,
        tourapi_tour_en_key=os.getenv("TOURAPI_TOUR_EN") or None,
        tourapi_guide_endpoint=os.getenv("TOURAPI_GUIDE_ENDPOINT", "https://apis.data.go.kr/B551011/TarRlteTarService1"),
        tourapi_rate_endpoint=os.getenv("TOURAPI_RATE_ENDPOINT", "https://apis.data.go.kr/B551011/TatsCnctrRateService"),
        tourapi_mdc_endpoint=os.getenv("TOURAPI_MDC_ENDPOINT", "https://apis.data.go.kr/B551011/KorService2"),
        tourapi_pet_endpoint=os.getenv("TOURAPI_PET_ENDPOINT", "https://apis.data.go.kr/B551011/KorPetTourService2"),
        tourapi_tour_endpoint=os.getenv("TOURAPI_TOUR_ENDPOINT", "https://apis.data.go.kr/B551011/KorService2"),
        tourapi_tour_en_endpoint=os.getenv("TOURAPI_TOUR_EN_ENDPOINT", "https://apis.data.go.kr/B551011/EngService2"),
        tourapi_base_ym=os.getenv("TOURAPI_BASE_YM", "202503"),
        ga_measurement_id=os.getenv("GA_MEASUREMENT_ID") or DEFAULT_GA_MEASUREMENT_ID,
        adsense_publisher_id=os.getenv("ADSENSE_PUBLISHER_ID") or None,
        post_count=int(os.getenv("BLOG_POST_COUNT", "5")),
        enable_llm_edit=os.getenv("ENABLE_LLM_EDIT", "true").lower() == "true",
        enable_image_generation=os.getenv("ENABLE_IMAGE_GENERATION", "false").lower() == "true",
        output_dir=Path(os.getenv("BLOG_OUTPUT_DIR", "output/posts")),
        assets_dir=Path(os.getenv("BLOG_ASSETS_DIR", "output/assets")),
        public_dir=Path(os.getenv("BLOG_PUBLIC_DIR", "public")),
        state_dir=Path(os.getenv("BLOG_STATE_DIR", "state")),
        site_title=os.getenv("BLOG_SITE_TITLE", "브리핑웨이브"),
        site_description=os.getenv("BLOG_SITE_DESCRIPTION", "브리핑웨이브에서 생활·기술·정책 소식을 쉽고 빠르게 확인하세요."),
        custom_domain=os.getenv("BLOG_CUSTOM_DOMAIN") or None,
        publisher=os.getenv("PUBLISHER", "markdown"),
        wordpress_url=os.getenv("WORDPRESS_URL") or None,
        wordpress_username=os.getenv("WORDPRESS_USERNAME") or None,
        wordpress_app_password=os.getenv("WORDPRESS_APP_PASSWORD") or None,
        wordpress_status=os.getenv("WORDPRESS_STATUS", "publish"),
        blogger_api_key=os.getenv("BLOGGER_API_KEY") or None,
        blogger_blog_id=os.getenv("BLOGGER_BLOG_ID") or None,
        blogger_oauth_client_id=os.getenv("BLOGGER_OAUTH_CLIENT_ID") or None,
        blogger_oauth_client_secret=os.getenv("BLOGGER_OAUTH_CLIENT_SECRET") or None,
        blogger_refresh_token=os.getenv("BLOGGER_REFRESH_TOKEN") or None,
        categories=[c.strip() for c in os.getenv("BLOG_CATEGORIES", ",".join(_DEFAULT_CATEGORIES)).split(",") if c.strip()],
    )
