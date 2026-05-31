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
- `WORDPRESS_STATUS`: `publish` 추천. 임시 저장이 필요할 때만 `draft`
- `WORDPRESS_POST_COUNT`: 기본값 `1`
- `WORDPRESS_MIN_QUALITY`: 기본값 `65`

바로 공개 발행하려면 `WORDPRESS_STATUS=publish`로 둡니다.

## 3. 수동 실행

GitHub 저장소에서:

`Actions → WordPress publish → Run workflow`

입력값:

- `count`: 테스트는 `1`
- `status`: 바로 공개하려면 `publish`
- `min_quality`: 기본 `65`

성공하면 Actions 로그의 `publish_results`에 WordPress 글 URL이 표시됩니다.

## 4. 자동 실행

`.github/workflows/wordpress-publish.yml`은 매일 00:30 KST에 실행됩니다.

기본값은 `publish`입니다. 임시 저장 운영이 필요한 경우에만 `draft`로 바꾸세요.

## 5. 실패 처리

워크플로는 `--require-publish-success` 옵션을 사용합니다. WordPress API 호출이 실패하면 GitHub Actions가 실패 상태로 끝납니다.

실행별 manifest와 품질 리포트는 artifact로 업로드되고, `state/*.json`, `output/reports/*.json`는 저장소에 커밋됩니다. SQLite 파일은 커밋하지 않습니다.
