# Hugging Face Space Console

Hugging Face Space는 공개 블로그 자체보다 **운영 콘솔**로 쓰는 것이 좋습니다.

- GitHub Pages: 개인 도메인 연결, 애드센스 대상 공개 사이트
- WordPress: REST API 자동 포스팅 대상 CMS
- Hugging Face Space: 초안 검수, 이미지 프롬프트/대표 이미지 생성 UI

Hugging Face 공식 문서에 따르면 Spaces는 Gradio 앱을 만들 수 있고, Secrets/Variables는 Space 설정에서 환경변수로 주입됩니다. GitHub Actions로 Space를 동기화할 수도 있습니다.

## 1. Space 만들기

Hugging Face에서 새 Space를 만듭니다.

- SDK: `Gradio`
- Visibility: 처음에는 `Private` 또는 `Public`
- Name: 예: `blog-agent-console`

Space ID 예시:

```text
icanjt7/blog-agent-console
```

## 2. GitHub Secrets / Variables

GitHub 저장소에서:

`Settings → Secrets and variables → Actions`

Secrets:

- `HF_TOKEN`: Hugging Face write token

Variables:

- `HF_SPACE_ID`: 예: `icanjt7/blog-agent-console`

이후 `Actions → Sync Hugging Face Space → Run workflow`를 실행하면 `hf_space/` 폴더가 Space로 업로드됩니다.

`HF_SPACE_ID`가 비어 있으면 업로드가 실패합니다. Space를 아직 만들지 않았다면 이 워크플로는 실행하지 않아도 됩니다. GitHub Pages 블로그와 Streamlit 대시보드 운영에는 Hugging Face Space가 필수는 아닙니다.

## 3. Space Secrets

Hugging Face Space의 Settings에서 Secrets를 등록합니다.

필수:

- `OPENAI_API_KEY`

선택:

- `OPENAI_MODEL`: 기본값 `gpt-4.1-mini`
- `OPENAI_IMAGE_TEXT_MODEL`: 기본값 `gpt-5`
- `BLOG_SITE_TITLE`

WordPress 발행 버튼까지 Space에서 직접 붙이고 싶다면 추가로 다음 값을 넣을 수 있습니다.

- `WORDPRESS_URL`
- `WORDPRESS_USERNAME`
- `WORDPRESS_APP_PASSWORD`

현재 Space 앱은 안전을 위해 직접 발행보다 초안/이미지 검수에 초점을 둡니다. 실제 발행은 GitHub Actions의 `Hybrid publish` 워크플로가 담당합니다.

## 4. 이미지 생성

Space의 `Image` 탭에서 글 제목과 본문 요약을 넣으면 대표 이미지 프롬프트를 만들고, `OPENAI_API_KEY`가 설정되어 있으면 이미지를 생성합니다.

OpenAI 이미지 생성은 GPT Image 계열 모델을 사용할 수 있습니다. 최신 문서 기준으로 `gpt-image-1.5`, `gpt-image-1`, `gpt-image-1-mini`가 이미지 생성 모델군이며, Responses API의 `image_generation` 도구로도 이미지를 만들 수 있습니다.

## 5. 운영 추천

초기 운영:

1. Space에서 초안과 이미지 콘셉트를 확인합니다.
2. GitHub Actions `Hybrid publish`를 `wordpress_status=draft`로 실행합니다.
3. WordPress와 GitHub Pages 결과를 확인합니다.
4. 안정되면 `WORDPRESS_STATUS=publish`로 전환합니다.

주의:

- Hugging Face Space의 무료 CPU는 사용하지 않으면 sleep 상태가 될 수 있습니다.
- Space 커스텀 도메인은 Pro/Team 기능입니다. 애드센스용 공개 블로그 도메인은 GitHub Pages에 연결하는 쪽이 더 적합합니다.
- API 키는 절대 코드에 넣지 말고 Space Secret 또는 GitHub Secret에만 저장하세요.
