# 브리핑웨이브 수집·가공·렌더링 개선 적용 가이드

## 변경 파일별 diff 요약

- `scripts/import_press_releases.py`: 부처 사전점수와 제목/본문 키워드 가중치, 정책 오분류 방어, 환경 카테고리 및 보도자료용 새 본문 템플릿을 추가했습니다.
- `blog_agent/models.py`, `blog_agent/trends.py`: 정식 `환경` 카테고리 타입과 기본 주제 시드를 추가했습니다.
- `blog_agent/retrieval.py`, `blog_agent/images.py`, `scripts/improve_existing_images.py`: 환경 카테고리의 공식 폴백 출처, 이미지 프롬프트, 유지보수 스크립트 허용값을 연결했습니다.
- `blog_agent/writer.py`, `blog_agent/editor.py`: 대상·혜택·일정·기관 4항목 요약 카드, 검색 질문형 헤딩, 주제별 체크리스트/FAQ, AI 상투어 금지를 생성·재편집 프롬프트와 규칙 기반 폴백에 반영했습니다.
- `blog_agent/site.py`: 모든 포스팅에 토스쇼핑 상품을 강제 배정하는 하드 폴백, 메인 공고 카드 아래의 순환 상품 스트립, 토스 블루 CTA·혜택 배지·후기 카드, 공식 출처 버튼, 입찰 카드/D-Day CSS·JS를 추가했습니다.
- `blog_agent/narabid.py`: 공고명·수요기관·추정금액·마감일시·링크를 반응형 카드로 출력하고 빌드 시점 D-Day를 계산합니다.
- `tests/test_press_releases.py`, `tests/test_site.py`, `tests/test_narabid.py`: 산업 보조금 분류, 환경/기술 라우팅, 전 포스팅 상품 하드 폴백, 출처 배지, 반응형 입찰 카드와 D-Day 회귀 테스트를 추가했습니다.

전체 패치는 저장소 루트에서 다음 명령으로 확인할 수 있습니다.

```powershell
git diff -- blog_agent scripts/import_press_releases.py scripts/improve_existing_images.py tests
```

## 적용 순서

```powershell
python -m pip install -e .
python -m pytest -q
python -m blog_agent.cli build-site
```

`build-site`는 `output/posts/`의 Markdown을 `public/`에 다시 렌더링합니다. 실제 배포 전 `public/index.html`, 나라장터 글 한 건, 정책/복지 글 한 건, 생활 상품 글 한 건을 모바일 너비에서 확인합니다.

## 조정 가능한 기준값

- 상품 순환 개수: `StaticSiteBuilder._select_products(..., limit=5)`
- 부처 우선점수와 키워드 점수: `classify_press_category()`
- 나라장터 추정금액 원본 필드: `BidNotice.budget_amount` 및 `_notice_from_item()`

분류나 상품 매칭 기준을 바꾼 뒤에는 반드시 전체 테스트와 정적 사이트 재빌드를 함께 실행합니다.
