# Hybrid GitHub Pages + WordPress Publishing

이 구성은 같은 글을 두 곳에 동시에 보냅니다.

- GitHub Pages: 개인 도메인을 붙일 공개 블로그
- WordPress: REST API로 자동 포스팅되는 CMS/검수/백업 채널

## Architecture

```mermaid
graph TD
    Actions[GitHub Actions] --> Agent[Blog Agent]
    Agent --> Markdown[Markdown Drafts]
    Agent --> WordPress[WordPress REST API]
    Markdown --> Site[Static Site Builder]
    Site --> Pages[GitHub Pages + Custom Domain]
```

## Required GitHub Secrets

`Settings → Secrets and variables → Actions → Secrets`

- `OPENAI_API_KEY`
- `WORDPRESS_URL`
- `WORDPRESS_USERNAME`
- `WORDPRESS_APP_PASSWORD`

## Recommended GitHub Variables

`Settings → Secrets and variables → Actions → Variables`

- `BLOG_SITE_TITLE`: 사이트명
- `BLOG_CUSTOM_DOMAIN`: 예: `example.com`
- `WORDPRESS_STATUS`: 처음에는 `draft`, 검증 후 `publish`
- `HYBRID_POST_COUNT`: 처음에는 `1`
- `HYBRID_MIN_QUALITY`: 기본 `65`

## First Run

1. GitHub Pages 설정에서 Source를 `GitHub Actions`로 설정합니다.
2. WordPress에서 Application Password를 만듭니다.
3. 위 Secrets와 Variables를 등록합니다.
4. `Actions → Hybrid publish → Run workflow`를 실행합니다.
5. 처음에는 `count=1`, `wordpress_status=draft`로 확인합니다.

성공하면:

- WordPress에는 draft 글이 생성됩니다.
- GitHub Pages에는 같은 글이 정적 HTML로 배포됩니다.
- `output/posts`, `output/reports`, `state/*.json`는 저장소에 기록됩니다.

## Custom Domain

`BLOG_CUSTOM_DOMAIN`을 설정하면 `public/CNAME` 파일이 자동 생성됩니다. DNS에는 GitHub Pages 안내에 맞춰 A/AAAA 또는 CNAME 레코드를 설정해야 합니다.

도메인 연결 전에는 기본 주소로 확인할 수 있습니다.

```text
https://icanjt7.github.io/blog/
```

도메인을 연결한 뒤에는 GitHub 저장소의 `Settings → Pages`에서 HTTPS 강제 적용을 켜세요.

## Operating Mode

초기 추천:

- GitHub Pages: 공개
- WordPress: `draft`

글 품질과 발행 결과가 안정되면:

- GitHub Pages: 공개
- WordPress: `publish`

WordPress 발행이 실패하면 워크플로가 실패 상태로 종료됩니다. GitHub Pages 배포도 같은 실행 안에 있으므로 처음에는 반드시 draft로 충분히 확인하세요.
