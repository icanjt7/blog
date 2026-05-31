# Streamlit Dashboard

Streamlit 앱은 블로그 자체가 아니라 운영 대시보드입니다.

주요 역할:

- WordPress 블로그 바로가기
- GitHub Pages 공개 블로그 바로가기
- 최근 생성 글 확인
- 품질 리포트 확인
- 실행 manifest 확인

## Main file path

Streamlit Community Cloud에서 Main file path는 다음으로 지정합니다.

```text
streamlit_app.py
```

## Secrets

Streamlit Cloud 앱 설정에서 Secrets에 다음 값을 넣으면 링크가 표시됩니다.

```toml
WORDPRESS_URL = "https://your-wordpress-site.com"
GITHUB_PAGES_URL = "https://icanjt7.github.io/blog/"
BLOG_CUSTOM_DOMAIN = "your-domain.com"
```

개인 도메인을 GitHub Pages에 연결했다면 `BLOG_CUSTOM_DOMAIN`만 넣어도 됩니다.

## Dashboard URL

Streamlit 앱을 배포하면 다음과 같은 주소가 생깁니다.

```text
https://앱이름.streamlit.app
```

정확한 주소는 Streamlit Cloud 배포 완료 화면에서 확인할 수 있습니다. 이 주소가 운영 대시보드 주소입니다.

블로그 방문자는 Streamlit 주소가 아니라 WordPress 또는 GitHub Pages 주소로 보내는 것이 좋습니다.
