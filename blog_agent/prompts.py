from __future__ import annotations

import json
import re
from typing import Any, Literal


PressTemplate = Literal["ACTIONABLE", "INFORMATIONAL", "ANNOUNCEMENT"]

_ANNOUNCEMENT_MARKERS = (
    "당선작", "선정 결과", "결과 발표", "최종 선정", "수상작", "건립", "착공", "준공",
    "개관", "확정", "지정", "승인", "법령", "시행령", "시행규칙", "제정", "개정", "고시", "공포",
)
_INFORMATIONAL_MARKERS = (
    "업무협약", "양해각서", "mou", "협약", "토론회", "간담회", "학술대회", "세미나",
    "포럼", "동향", "회의", "캠페인", "전시", "공연", "기념식", "축제",
)
_ACTIONABLE_MARKERS = (
    "지원금", "보조금", "장려금", "바우처", "감면", "환급", "융자", "공모", "모집",
    "신청", "접수", "지원사업", "지원 사업", "복지", "급여", "수당",
)
_FORBIDDEN_EMPTY_VALUES = ("공식 원문 참조", "공식 원문 확인", "해당 없음", "미정", "확인 필요")
_FORBIDDEN_CLICHES = ("이 기사는 시사합니다", "종합적으로 볼 때")


def classify_press_template(title: str, body: str = "") -> PressTemplate:
    """보도자료를 행동형·정보형·결과발표형으로 분류한다."""

    title_text = re.sub(r"\s+", " ", title).strip().casefold()
    body_text = re.sub(r"\s+", " ", body).strip().casefold()
    # '설계공모 당선작'처럼 공모와 결과 발표가 함께 나오면 결과 발표를 우선한다.
    if any(marker in title_text for marker in _ANNOUNCEMENT_MARKERS):
        return "ANNOUNCEMENT"
    if any(marker in title_text for marker in _INFORMATIONAL_MARKERS):
        return "INFORMATIONAL"
    if any(marker in title_text for marker in _ACTIONABLE_MARKERS):
        return "ACTIONABLE"

    scores = {
        "ANNOUNCEMENT": sum(marker in body_text for marker in _ANNOUNCEMENT_MARKERS),
        "INFORMATIONAL": sum(marker in body_text for marker in _INFORMATIONAL_MARKERS),
        "ACTIONABLE": sum(marker in body_text for marker in _ACTIONABLE_MARKERS),
    }
    priority = {"ANNOUNCEMENT": 2, "INFORMATIONAL": 1, "ACTIONABLE": 0}
    best = max(scores, key=lambda item: (scores[item], priority[item]))
    return best if scores[best] else "INFORMATIONAL"  # type: ignore[return-value]


def press_template_instruction(template: PressTemplate) -> str:
    common = """[보도자료 3분류 및 헤딩 규칙]
- H2/H3는 고정 문구를 복사하지 말고 원문의 고유명사·장소·사업명·수치를 포함한 검색 질문형 문장으로 작성한다.
- 핵심 3줄 요약을 H1 바로 아래 본문의 첫 블록으로 배치하고, 서론보다 핵심 대상·금액·날짜·결과를 먼저 제시한다.
- '결론적으로', '요약하자면', '이 영화가 주는 메시지는', '종합해 보면' 같은 AI 상투어를 사용하지 않는다.
- 요약 값은 공식 자료에서 확인되는 사실만 쓴다. 정보가 없으면 사실을 만들지 말고, 원문에 있는 다른 핵심 사실로 라벨과 값을 함께 교체한다.
- '공식 원문 참조', '공식 원문 확인', '해당 없음', '미정', '확인 필요'는 요약 박스에 절대 출력하지 않는다.
"""
    if template == "ACTIONABLE":
        return common + """- post_type: ACTIONABLE — 개인·기업이 혜택을 받기 위해 신청하는 지원금·복지·모집
- 요약 라벨 기준: [지원 대상], [핵심 혜택·금액], [신청 방법·기한]
- 전개 순서: 지원 대상 요건 → 지원 내용 → 신청 절차 → FAQ
"""
    if template == "ANNOUNCEMENT":
        return common + """- post_type: ANNOUNCEMENT — 당선작·결과 발표·인프라 건립·법령 제정/개정/고시
- 요약 라벨 기준: [당선작·핵심 결과], [사업 규모·위치], [향후 추진·완공 일정]
- 일정이 없으면 [심사 평가], [설계 콘셉트], [주요 시설], [기대 효과]처럼 원문에 있는 사실로 라벨을 교체한다.
- 전개 순서: 선정 결과와 심사 평가·설계 콘셉트 → 주요 시설과 사업 규모 → 향후 추진·완공 일정
"""
    return common + """- post_type: INFORMATIONAL — 기관 간 MOU·학술대회·토론회·일회성 문화 행사
- 요약 라벨 기준: [참여 기관], [협약·행사 목적], [개최 일정·장소]
- 일정·장소가 없으면 [주요 협력 내용] 또는 [기대 효과]처럼 원문에 있는 사실로 라벨을 교체한다.
- 전개 순서: 행사·협약 목적 → 주요 논의·협력 내용 → 기대 효과
"""


def press_summary_card_instruction(template: PressTemplate) -> str:
    labels = {
        "ACTIONABLE": "[지원 대상] / [핵심 혜택·금액] / [신청 방법·기한]",
        "INFORMATIONAL": "[참여 기관] / [협약·행사 목적] / [개최 일정·장소]",
        "ANNOUNCEMENT": "[당선작·핵심 결과] / [사업 규모·위치] / [향후 추진·완공 일정]",
    }[template]
    return (
        f"도입보다 먼저, H1 바로 아래에 {labels} 성격의 요약 3개를 둔다. "
        "원문에 없는 항목은 원문에 있는 다른 핵심 사실로 라벨과 값을 함께 교체한다. "
        "빈 값이나 대체 문구는 금지한다."
    )


def press_localization_instruction(template: PressTemplate) -> str:
    """Return the shared localization contract for policy/news generation paths."""

    if template not in {"ACTIONABLE", "INFORMATIONAL"}:
        return ""
    return """[해외 정책·경제 동향 지역화 규칙]
- 출처 기관과 정책 대상국을 판별한다. FTC, SEC, EU 집행위원회 등 해외 기관 자료면 해외 자료로 표시한다.
- 해외 자료의 첫 번째 H2는 반드시 '핵심 내용과 국내 파급력'으로 둔다.
- 해당 H2 아래에 원문으로 확인된 핵심 내용과 한국 산업·기업·소비자에게 생길 수 있는 간접 영향을 1~2문장으로 쓴다.
- 국내 파급력은 합리적 추론임을 '가능성이 있다', '확인할 필요가 있다'처럼 분명히 표시한다. 원문에 없는 사실·수치·확정적 인과관계는 만들지 않는다.
- Rulemaking, FTC처럼 한국 독자에게 낯선 용어가 있으면 본문 중간에 '> 💡 **핵심 용어: 용어명** - 쉬운 해설' 형식의 인용문을 둔다.
- 마지막 정보 단락은 정확히 '## 에디터의 시사점 (Key Takeaways)'으로 시작하고, 독자가 확인하거나 대응할 항목 3개를 Markdown 불릿으로 쓴다.
- '이 기사는 ~를 시사합니다', '종합적으로 볼 때' 같은 기계적인 맺음말은 사용하지 않는다.
"""


def press_json_system_prompt() -> str:
    """보도자료 작성 모델에 전달하는 단일 JSON 출력 계약."""

    return """당신은 공공기관 보도자료를 구조화하는 한국어 편집기다.
원문을 읽고 post_type을 ACTIONABLE, INFORMATIONAL, ANNOUNCEMENT 중 하나로 판단한다.
핵심 3줄 요약(summary_box)은 H1 바로 아래에서 가장 먼저 렌더링될 데이터이므로 결론이나 배경보다 수혜 대상·금액·일정·핵심 결과를 앞에 배치한다.
절대로 '결론적으로', '요약하자면', '이 영화가 주는 메시지는', '종합해 보면', '이 기사는 ~를 시사합니다', '종합적으로 볼 때' 같은 기계적이고 상투적인 서두/맺음말(AI Cliché)을 사용하지 말 것. 전문적이고 건조한 블로거의 문체를 유지하고 바로 팩트와 수치를 제시할 것.

제공된 보도자료 원문 텍스트가 구체적인 사실(Fact), 수치, 정책 내용을 포함하지 않고 단순히 '00월호가 발간되었습니다' 수준의 안내에 그친다면, 억지로 소제목(H2)이나 요약을 지어내지 말고 JSON 응답의 'post_type'을 'INVALID_DATA'로 반환할 것.
INVALID_DATA인 경우에는 {"post_type":"INVALID_DATA","reason":"구체적 원문 부족"}만 출력한다.

분류 규칙:
1. ACTIONABLE: 개인·기업이 혜택을 받기 위해 신청해야 하는 지원금·복지·접수·모집. 별도 POLICY 유형을 만들지 않고 신청형 정책은 ACTIONABLE로 처리한다.
2. INFORMATIONAL: 기관 간 MOU, 학술대회, 토론회, 일회성 행사.
3. ANNOUNCEMENT: 설계공모 당선작·선정 결과, 센터/기념관 건립, 법령 제·개정 또는 고시.
   제목에 '공모'가 있어도 이미 당선작이나 결과가 발표됐다면 ANNOUNCEMENT다.

반드시 설명이나 Markdown 코드펜스 없이 아래 형태의 유효한 JSON 객체 하나만 출력한다.
{
  "post_type": "ACTIONABLE | INFORMATIONAL | ANNOUNCEMENT | INVALID_DATA",
  "source_scope": "DOMESTIC | FOREIGN",
  "title": "30자 안팎의 구체적인 제목",
  "excerpt": "핵심 결과를 담은 2문장 요약",
  "lead": "기관·발표일·핵심 결과가 들어간 도입 문단",
  "summary_box": [
    {"label": "동적 라벨 1", "value": "원문에서 확인한 구체적 사실"},
    {"label": "동적 라벨 2", "value": "원문에서 확인한 구체적 사실"},
    {"label": "동적 라벨 3", "value": "원문에서 확인한 구체적 사실"}
  ],
  "key_facts": [
    "원문에서 확인한 날짜·금액·규모·대상 등 객관적 사실 1",
    "원문에서 확인한 객관적 사실 2",
    "원문에서 확인한 객관적 사실 3"
  ],
  "local_impact": "해외 자료일 때 한국 산업·기업·소비자에 대한 간접 영향 1~2문장, 국내 자료면 빈 문자열",
  "glossary": [
    {"term": "FTC", "explanation": "미국의 소비자 보호와 경쟁 정책을 담당하는 연방거래위원회"}
  ],
  "sections": [
    {"heading": "원문 고유명사가 포함된 H2", "body_markdown": "근거 중심 본문"}
  ],
  "takeaways": [
    "독자가 확인하거나 대응할 항목 1",
    "독자가 확인하거나 대응할 항목 2",
    "독자가 확인하거나 대응할 항목 3"
  ]
}

summary_box는 정확히 3개를 출력한다.
key_facts는 원문에서 직접 확인되는 날짜·예산·규모·인원·평점 등 객관적 수치와 사실만 3~4개 출력한다. 수치가 부족하면 기관·대상·장소처럼 검증 가능한 사실을 사용하며 창작하지 않는다.
ACTIONABLE sections는 최소 4개이며 지원 대상 요건 → 지원 내용 → 신청 절차 → FAQ 순서를 지킨다.
INFORMATIONAL sections는 최소 3개이며 목적 → 주요 논의·협력 내용 → 기대 효과 순서를 지킨다.
ANNOUNCEMENT sections는 최소 3개이며 선정 결과 → 시설·사업 규모 → 향후 추진 일정 순서를 지킨다.
ACTIONABLE 또는 INFORMATIONAL이 해외 정부·기관의 정책·경제 자료라면 source_scope를 FOREIGN으로 지정한다.
FOREIGN 자료의 local_impact에는 한국 산업·기업·소비자에게 생길 수 있는 간접 영향을 1~2문장으로 작성하되, 반드시 추론임을 구분하고 원문에 없는 수치나 확정적 사실을 만들지 않는다. 렌더러는 이를 첫 번째 H2 '핵심 내용과 국내 파급력' 아래에 배치한다.
낯선 행정·전문 용어가 있으면 glossary에 용어와 한국 독자가 이해하기 쉬운 한 문장 해설을 넣는다. 용어가 없으면 빈 배열을 출력한다.
ACTIONABLE과 INFORMATIONAL의 takeaways는 정확히 3개이며, 마지막 '에디터의 시사점 (Key Takeaways)' H2 아래의 불릿 목록으로 렌더링될 구체적인 확인·대응 항목을 쓴다.
모든 section heading은 '개요', '지원 내용', '신청 방법' 같은 고정 문구만 쓰지 말고 원문의 사업명·대상·지역·수치를 포함한 검색 질문형 제목으로 만든다.
ACTIONABLE 라벨은 지원 대상·혜택/금액·신청 방법/기한을 우선한다.
INFORMATIONAL 라벨은 참여 기관·목적·일정/장소를 우선한다.
ANNOUNCEMENT 라벨은 당선작/결과·사업 규모/위치·추진/완공 일정을 우선한다.
특정 정보가 원문에 없으면 원문의 다른 중요한 사실(심사 평가, 설계 콘셉트, 주요 시설, 총사업비, 기대 효과 등)로 라벨과 값을 함께 교체한다.
'공식 원문 참조', '공식 원문 확인', '해당 없음', '미정', '확인 필요'는 절대 출력하지 않는다.
출처에 없는 사실·수치·일정은 창작하지 않는다. 단, FOREIGN 자료의 local_impact만 원문 사실을 근거로 한 제한적 추론을 허용하며 사실과 명확히 구분한다."""


def parse_press_json(text: str, expected_type: PressTemplate | None = None) -> dict[str, Any] | None:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(payload, dict) or payload.get("post_type") not in {
        "ACTIONABLE", "INFORMATIONAL", "ANNOUNCEMENT", "INVALID_DATA"
    }:
        return None
    if payload["post_type"] == "INVALID_DATA":
        return payload
    if expected_type and payload["post_type"] != expected_type:
        return None
    summaries = payload.get("summary_box")
    key_facts = payload.get("key_facts")
    sections = payload.get("sections")
    if not isinstance(summaries, list) or len(summaries) != 3:
        return None
    if not isinstance(key_facts, list) or not 3 <= len(key_facts) <= 4:
        return None
    if any(not str(fact).strip() for fact in key_facts):
        return None
    minimum_sections = 4 if payload["post_type"] == "ACTIONABLE" else 3
    if not isinstance(sections, list) or len(sections) < minimum_sections:
        return None
    for item in summaries:
        if not isinstance(item, dict):
            return None
        label = str(item.get("label") or "").strip()
        value = str(item.get("value") or "").strip()
        if not label or not value or any(marker in value for marker in _FORBIDDEN_EMPTY_VALUES):
            return None
    for section in sections:
        if not isinstance(section, dict) or not str(section.get("heading") or "").strip():
            return None
        if not str(section.get("body_markdown") or "").strip():
            return None
    scope = str(payload.get("source_scope") or "DOMESTIC").strip().upper()
    if scope not in {"DOMESTIC", "FOREIGN"}:
        return None
    if payload["post_type"] in {"ACTIONABLE", "INFORMATIONAL"}:
        takeaways = payload.get("takeaways")
        if not isinstance(takeaways, list) or len(takeaways) != 3:
            return None
        if any(not str(item).strip() for item in takeaways):
            return None
        if scope == "FOREIGN" and not str(payload.get("local_impact") or "").strip():
            return None
    glossary = payload.get("glossary", [])
    if not isinstance(glossary, list):
        return None
    for item in glossary:
        if not isinstance(item, dict):
            return None
        if not str(item.get("term") or "").strip() or not str(item.get("explanation") or "").strip():
            return None
    serialized = json.dumps(payload, ensure_ascii=False)
    if any(cliche in serialized for cliche in _FORBIDDEN_CLICHES):
        return None
    return payload


def render_press_json(payload: dict[str, Any], source_markdown: str = "") -> str:
    lead = str(payload.get("lead") or "").strip()
    summary = "\n>\n".join(
        f"> **[{str(item['label']).strip().strip('[]')}]** {str(item['value']).strip()}"
        for item in payload["summary_box"]
    )
    key_facts = "## 핵심 팩트 (Key Facts)\n\n" + "\n".join(
        f"- {str(item).strip()}" for item in payload["key_facts"]
    )
    scope = str(payload.get("source_scope") or "DOMESTIC").strip().upper()
    local_impact = str(payload.get("local_impact") or "").strip()
    impact = ""
    if scope == "FOREIGN" and local_impact:
        impact = "## 핵심 내용과 국내 파급력\n\n" + local_impact

    rendered_sections = [
        f"## {str(item['heading']).strip().lstrip('#').strip()}\n\n{str(item['body_markdown']).strip()}"
        for item in payload["sections"]
    ]
    glossary = "\n>\n".join(
        f"> 💡 **핵심 용어: {str(item['term']).strip()}** - {str(item['explanation']).strip()}"
        for item in payload.get("glossary", [])
    )
    if glossary:
        rendered_sections.insert(1 if rendered_sections else 0, glossary)
    sections = "\n\n".join(rendered_sections)
    takeaways = payload.get("takeaways") or []
    takeaway_block = ""
    if takeaways:
        takeaway_block = "## 에디터의 시사점 (Key Takeaways)\n\n" + "\n".join(
            f"- {str(item).strip()}" for item in takeaways
        )
    # The summary must be the first body block so the renderer can place it
    # directly below the H1 without searching through introductory prose.
    return "\n\n".join(
        part for part in (summary, lead, impact, key_facts, sections, source_markdown.strip(), takeaway_block) if part
    ).strip()
