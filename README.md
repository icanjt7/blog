# Blog Auto Agent

하루 5편의 블로그 콘텐츠를 자동으로 기획, 수집, 작성, 검수, 발행하는 Python 기반 에이전트입니다.

기본 설계는 다음 원칙을 따릅니다.

- 지속 가능한 데이터 수급: RSS, 공식 보도자료, 공공 API, GitHub/뉴스 피드 등 안정적인 소스 우선
- 자연스러운 글쓰기: 카테고리별 페르소나와 문체 규칙 적용
- 안전한 발행: 초안 저장, 품질 점수 검수, 중복 주제 방지 후 플랫폼 어댑터로 발행
- GitHub 운영: GitHub Actions로 매일 자동 실행 가능

## 빠른 시작

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
python -m blog_agent.cli run --count 5 --dry-run
```

초안은 `output/posts/`에 Markdown 파일로 저장됩니다.

## GitHub Pages 블로그 운영

웹호스팅 없이 GitHub 저장소만으로 자동 블로그를 운영할 수 있습니다.

```bash
python -m blog_agent.cli run --count 5 --publisher markdown
python -m blog_agent.cli build-site
```

`build-site`는 `output/posts/`의 Markdown 글을 `public/` 정적 사이트로 렌더링합니다. GitHub Actions는 매일 글을 만들고, `public/`을 GitHub Pages에 배포합니다.

GitHub 저장소 Settings → Pages에서 Source를 `GitHub Actions`로 설정하세요. 배포 후 주소는 보통 `https://icanjt7.github.io/blog/` 형태가 됩니다.

## 실제 발행

```bash
python -m blog_agent.cli run --count 5 --publisher markdown
```

현재 기본 발행기는 `markdown`입니다. WordPress REST API는 바로 사용할 수 있고, 티스토리/네이버는 정책과 인증 방식이 자주 바뀌므로 `blog_agent/publishers.py`의 어댑터를 확장하도록 분리했습니다.

WordPress 발행 검증은 로컬 Docker 환경에서 먼저 할 수 있습니다.

```bash
docker compose -f docker-compose.wordpress.yml up -d
```

자세한 절차는 [docs/wordpress-local-test.md](docs/wordpress-local-test.md)를 참고하세요.

## 환경변수

필수:

- `OPENAI_API_KEY`: LLM 생성에 사용합니다. 없으면 규칙 기반 초안 생성기로 동작합니다.

선택:

- `OPENAI_MODEL`: 기본값 `gpt-4.1-mini`
- `BLOG_OUTPUT_DIR`: 기본값 `output/posts`
- `BLOG_PUBLIC_DIR`: 기본값 `public`
- `BLOG_SITE_TITLE`: 기본값 `Curieux Auto Blog`
- `WORDPRESS_URL`: 예: `https://example.com`
- `WORDPRESS_USERNAME`
- `WORDPRESS_APP_PASSWORD`
- `WORDPRESS_STATUS`: `draft` 또는 `publish`, 기본값 `publish`
- `PUBLISHER`: `markdown` 또는 `wordpress`

## GitHub Actions

`.github/workflows/daily-publish.yml`가 매일 00:10 KST에 실행되도록 설정되어 있습니다. 이 워크플로는 글 생성, 초안 커밋, GitHub Pages 배포까지 수행합니다.

GitHub 저장소 Settings → Secrets and variables → Actions에 다음 값을 등록하세요.

- `OPENAI_API_KEY`
- WordPress 사용 시 `WORDPRESS_URL`, `WORDPRESS_USERNAME`, `WORDPRESS_APP_PASSWORD`

## 실행 기록 확인

각 실행은 `state/runs.sqlite3`에 저장되고, 실행별 manifest와 품질 리포트가 JSON으로 남습니다.

```bash
python -m blog_agent.cli status
```

아키텍처는 [docs/architecture.md](docs/architecture.md)에 정리되어 있습니다.

## Docker

```bash
docker build -t blog-auto-agent .
docker run --env-file .env blog-auto-agent
```

## 카테고리 전략

초기 추천 비중:

- 생활정보/지원금: 공식 자료 기반이라 안정적
- IT/가전/테크: RSS와 공식 스펙 기반으로 자동화 적합
- 금융/재테크: 수치 검증이 필요하므로 보수적 템플릿 사용
- 맛집/여행: 직접 방문 표현 금지, 공개 리뷰/장소 데이터 분석형 콘텐츠로만 작성

## 주의

네이버 블로그 자동 발행은 공식적으로 안정적인 공개 쓰기 API가 제한적입니다. 브라우저 자동화로 로그인 세션을 조작하는 방식은 계정 제재와 약관 이슈가 생길 수 있어 기본 구현에서 제외했습니다. 대신 초안 생성 후 수동 업로드, 또는 허용된 API가 있는 플랫폼으로 발행하는 방식을 권장합니다.
