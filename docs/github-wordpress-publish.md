# GitHub Actions WordPress Publishing

GitHub Actions에서 WordPress REST API로 직접 포스팅하는 설정입니다. 로컬 PC나 Docker가 켜져 있을 필요가 없습니다.

## 1. WordPress Application Password 만들기

WordPress 관리자에서:

`Users → Profile → Application Passwords`

`blog-agent` 같은 이름으로 새 Application Password를 생성합니다. 생성된 비밀번호는 한 번만 보이므로 바로 GitHub Secret에 넣습니다.

## 2. GitHub Secrets 등록

저장소에서:

`Settings → Secrets and variables → Actions → New repository secret`

필수 Secrets:

- `OPENAI_API_KEY`
- `WORDPRESS_URL`: 예: `https://example.com`
- `WORDPRESS_USERNAME`: WordPress 사용자명
- `WORDPRESS_APP_PASSWORD`: Application Password

선택 Variables:

- `OPENAI_MODEL`: 기본값 `gpt-4.1-mini`
- `WORDPRESS_STATUS`: `draft` 또는 `publish`, 추천 기본값 `draft`
- `WORDPRESS_POST_COUNT`: 기본값 `1`
- `WORDPRESS_MIN_QUALITY`: 기본값 `65`

처음에는 반드시 `WORDPRESS_STATUS=draft`로 검증하세요.

## 3. 수동 실행

GitHub 저장소에서:

`Actions → WordPress publish → Run workflow`

입력값:

- `count`: 테스트는 `1`
- `status`: 테스트는 `draft`
- `min_quality`: 기본 `65`

성공하면 Actions 로그의 `publish_results`에 WordPress 글 URL이 표시됩니다.

## 4. 자동 실행

`.github/workflows/wordpress-publish.yml`은 매일 00:30 KST에 실행됩니다.

처음에는 `draft`로 며칠 돌려보고, WordPress 관리자에서 글 품질을 확인한 뒤 `WORDPRESS_STATUS=publish`로 바꾸는 것을 권장합니다.

## 5. 실패 처리

워크플로는 `--require-publish-success` 옵션을 사용합니다. WordPress API 호출이 실패하면 GitHub Actions가 실패 상태로 끝납니다.

실행별 manifest와 품질 리포트는 artifact로 업로드되고, `state/*.json`, `output/reports/*.json`는 저장소에 커밋됩니다. SQLite 파일은 커밋하지 않습니다.
