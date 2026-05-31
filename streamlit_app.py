from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import urljoin

import streamlit as st


ROOT = Path(__file__).parent
POSTS_DIR = ROOT / "output" / "posts"
REPORTS_DIR = ROOT / "output" / "reports"
STATE_DIR = ROOT / "state"


def get_setting(name: str, default: str = "") -> str:
    if name in st.secrets:
        return str(st.secrets[name])
    return os.getenv(name, default)


def load_json_files(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    items = []
    for path in sorted(directory.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_file"] = str(path.relative_to(ROOT))
            items.append(data)
        except json.JSONDecodeError:
            continue
    return items


def load_posts() -> list[dict[str, str]]:
    if not POSTS_DIR.exists():
        return []
    posts = []
    for path in sorted(POSTS_DIR.glob("*.md"), reverse=True):
        raw = path.read_text(encoding="utf-8")
        title = path.stem
        category = ""
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) == 3:
                for line in parts[1].splitlines():
                    if line.startswith("title:"):
                        title = line.split(":", 1)[1].strip().strip('"')
                    if line.startswith("category:"):
                        category = line.split(":", 1)[1].strip().strip('"')
        posts.append({"title": title, "category": category, "file": str(path.relative_to(ROOT))})
    return posts


def wordpress_api_url(wordpress_url: str) -> str:
    if not wordpress_url:
        return ""
    return urljoin(wordpress_url.rstrip("/") + "/", "wp-json/wp/v2/posts?per_page=5")


def main() -> None:
    st.set_page_config(page_title="브리핑웨이브 운영실", page_icon="📝", layout="wide")

    wordpress_url = get_setting("WORDPRESS_URL")
    pages_url = get_setting("GITHUB_PAGES_URL")
    custom_domain = get_setting("BLOG_CUSTOM_DOMAIN")
    public_url = f"https://{custom_domain}" if custom_domain else pages_url

    st.title("브리핑웨이브 운영실")
    st.caption("WordPress 포스팅과 GitHub Pages 공개 채널 상태를 확인합니다.")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Markdown posts", len(load_posts()))
    reports = load_json_files(REPORTS_DIR)
    manifests = load_json_files(STATE_DIR)
    with col2:
        st.metric("Quality reports", len(reports))
    with col3:
        st.metric("Run manifests", len(manifests))

    st.subheader("Live Links")
    link_cols = st.columns(3)
    with link_cols[0]:
        if wordpress_url:
            st.link_button("Open WordPress blog", wordpress_url, use_container_width=True)
            st.caption(wordpress_url)
        else:
            st.info("WORDPRESS_URL secret을 설정하면 WordPress 링크가 표시됩니다.")
    with link_cols[1]:
        if public_url:
            st.link_button("Open GitHub Pages blog", public_url, use_container_width=True)
            st.caption(public_url)
        else:
            st.info("GITHUB_PAGES_URL 또는 BLOG_CUSTOM_DOMAIN을 설정하세요.")
    with link_cols[2]:
        if wordpress_url:
            st.link_button("Open WordPress REST posts", wordpress_api_url(wordpress_url), use_container_width=True)
            st.caption("최근 WordPress 글 API")

    st.divider()

    left, right = st.columns([1, 1])
    with left:
        st.subheader("Recent Generated Posts")
        posts = load_posts()
        if posts:
            for post in posts[:10]:
                st.write(f"**{post['title']}**")
                st.caption(f"{post['category']} · {post['file']}")
        else:
            st.warning("아직 `output/posts`에 생성된 글이 없습니다.")

    with right:
        st.subheader("Latest Quality Report")
        if reports:
            latest = reports[0]
            st.metric("Average quality", latest.get("average_quality", 0))
            for draft in latest.get("drafts", [])[:5]:
                st.write(f"**{draft.get('title', '')}**")
                st.caption(
                    f"keyword: {draft.get('keyword', '')} · "
                    f"quality: {draft.get('quality_score', '')} · "
                    f"sources: {draft.get('source_count', 0)}"
                )
        else:
            st.warning("아직 품질 리포트가 없습니다.")

    st.subheader("Latest Run Manifest")
    if manifests:
        st.json(manifests[0], expanded=False)
    else:
        st.info("아직 실행 manifest가 없습니다.")


if __name__ == "__main__":
    main()
