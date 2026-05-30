# Local WordPress Test

도메인이나 유료 호스팅 없이 WordPress 자동 포스팅을 검증하는 절차입니다.

## 1. WordPress 실행 및 초기 설정

```bash
./scripts/setup_local_wordpress.sh
```

브라우저에서 `http://localhost:8080`을 열면 로컬 WordPress가 보입니다.

기본 테스트 계정:

- Site title: `Blog Agent Test`
- Username: `admin`
- Password: `admin-password-change-me`

스크립트는 WordPress 설치와 Application Password 생성을 자동으로 처리하고 `.env.wordpress.local` 파일을 만듭니다.

처음 테스트할 때는 `WORDPRESS_STATUS=draft`를 권장합니다. 정상 확인 후 `publish`로 바꾸면 바로 발행됩니다.

## 2. 테스트 포스팅

```bash
source .venv/bin/activate
set -a && source .env.wordpress.local && set +a
python -m blog_agent.cli run --count 1 --publisher wordpress
```

성공하면 JSON 결과의 `publish_results[0].url`에 글 주소가 표시됩니다.

## 3. 정리

```bash
docker compose -f docker-compose.wordpress.yml down
```

데이터까지 모두 삭제하려면:

```bash
docker compose -f docker-compose.wordpress.yml down -v
```

## 운영 판단

로컬 WordPress에서 정상 포스팅이 확인되면 다음 선택지가 있습니다.

- GitHub Pages 계속 운영: 무료, 애드센스는 도메인 연결 후 신청
- WordPress 유료 호스팅 이전: REST API 발행은 그대로 사용 가능
- WordPress는 검수용 CMS로만 사용하고 최종 공개는 GitHub Pages로 배포
