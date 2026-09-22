from __future__ import annotations

import re
from typing import Literal


PressTemplate = Literal["actionable", "informational"]

_INFORMATIONAL_MARKERS = (
    "업무협약",
    "양해각서",
    "mou",
    "협약",
    "토론회",
    "간담회",
    "세미나",
    "포럼",
    "동향",
    "회의",
    "캠페인",
    "전시",
    "공연",
    "기념식",
)
_ACTIONABLE_MARKERS = (
    "지원금",
    "보조금",
    "장려금",
    "바우처",
    "감면",
    "환급",
    "융자",
    "공모",
    "모집",
    "신청",
    "접수",
    "지원사업",
    "지원 사업",
    "제도",
)


def classify_press_template(title: str, body: str = "") -> PressTemplate:
    """보도자료의 독자 행동 가능 여부를 분류한다.

    제목의 협약·행사 신호를 가장 강하게 본다. MOU 본문에 등장하는
    '지원' 같은 일반 단어가 지원사업으로 오분류되는 일을 막기 위해서다.
    """

    title_text = re.sub(r"\s+", " ", title).strip().casefold()
    body_text = re.sub(r"\s+", " ", body).strip().casefold()
    if any(marker in title_text for marker in _INFORMATIONAL_MARKERS):
        return "informational"
    if any(marker in title_text for marker in _ACTIONABLE_MARKERS):
        return "actionable"

    informational_score = sum(marker in body_text for marker in _INFORMATIONAL_MARKERS)
    actionable_score = sum(marker in body_text for marker in _ACTIONABLE_MARKERS)
    if actionable_score > informational_score:
        return "actionable"
    return "informational"


def press_template_instruction(template: PressTemplate) -> str:
    common = """[보도자료 유형 및 헤딩 규칙]
- 먼저 보도자료 성격을 판단하고 아래에서 지정한 유형의 구조만 사용한다.
- H2/H3에 '핵심 내용', '주요 지원 내용', '향후 계획' 같은 고정 문구를 그대로 쓰지 않는다.
- 모든 H2/H3는 원문의 고유명사·장소·사업명·수치 중 하나를 포함해 검색 의도에 맞는 구체적인 문장으로 만든다.
- 예: 'WTC Seoul 코엑스 전광판은 국가유산 홍보에 어떻게 쓰이나요?'
"""
    if template == "informational":
        return common + """- 판정 유형: 유형 B — MOU·협약·토론회·행사·동향 등 Informational 정보
- 요약 카드에 지원 대상·금액·신청 방법을 만들지 않는다.
- 본문은 ① 협약/행사의 목적과 의의 ② 주요 협력 내용과 세부 사항 ③ 향후 기대 효과와 계획 순서로 전개한다.
- 독자에게 신청을 권하거나 필수 서류를 안내하지 않는다. 원문에 실제 참여 접수가 있을 때만 해당 사실을 별도로 적는다.
"""
    return common + """- 판정 유형: 유형 A — 지원금·제도·공모 등 Actionable 정보
- 본문은 ① 핵심 수혜 대상과 금액 ② 주요 지원 내용 ③ 신청 방법과 필수 서류 ④ FAQ 순서로 전개한다.
- 원문에 없는 금액, 자격, 일정, 서류는 추측하지 말고 '공식 원문 확인'이라고 표시한다.
"""


def press_summary_card_instruction(template: PressTemplate) -> str:
    if template == "informational":
        return """도입 한 문장 다음에는 아래 3항목 요약 카드를 둔다.
  > **[목적·의의]** ...
  > **[주요 협력·행사 내용]** ...
  > **[향후 계획]** ...
원문에 없는 지원 대상·금액·신청 일정 항목은 만들지 않는다."""
    return """도입 한 문장 다음에는 아래 4항목 요약 카드를 둔다. 원문에 값이 없으면 '공식 원문 확인'이라고 쓴다.
  > **[핵심 수혜 대상·금액]** ...
  > **[주요 지원 내용]** ...
  > **[신청 방법·필수 서류]** ...
  > **[주관 기관·신청처]** ..."""
