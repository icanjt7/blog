from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "import_press_releases.py"
SPEC = importlib.util.spec_from_file_location("import_press_releases", SCRIPT_PATH)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class PressReleaseImportTest(unittest.TestCase):
    def test_with_particle_uses_final_consonant(self) -> None:
        self.assertEqual(MODULE.with_particle("행정안전부", "이", "가"), "행정안전부가")
        self.assertEqual(MODULE.with_particle("국가유산청", "이", "가"), "국가유산청이")

    def test_finalize_article_body_keeps_llm_enriched_article(self) -> None:
        body = """행정안전부가 2026-06-14 공개한 재난안전 점검 발표입니다. 전국 17개 시도와 관계기관이 참여하며 6월 말까지 현장 점검을 진행합니다.

## 발표 내용

행정안전부는 여름철 위험지역을 중심으로 사전 점검 대상을 구분했습니다.

## 세부 내용

| 구분 | 확인할 내용 |
|---|---|
| 대상 | 전국 17개 시도 |
| 기간 | 6월 말까지 |

## 숫자와 일정

6월 말까지 현장 점검을 마치고 후속 조치를 안내합니다.

## 확인할 점

- 거주 지역이 점검 대상에 포함되는지 확인합니다.
- 후속 공지의 시행일을 확인합니다.

## 독자가 볼 부분

이 발표는 여름철 집중호우와 폭염에 대비해 지방자치단체와 관계기관이 어떤 역할을 나눠 맡는지 보여줍니다. 특히 전국 17개 시도, 위험지역, 현장 점검, 6월 말이라는 기준이 함께 제시되어 있어 독자는 자신의 거주 지역 공지와 연결해 볼 수 있습니다. 현장 점검 결과에 따라 보완 조치가 추가될 수 있으므로 지역 재난 문자, 지방자치단체 누리집, 행정안전부 후속 발표를 함께 확인하는 것이 좋습니다.

관계기관이 함께 움직이는 발표는 단순 안내보다 실행 일정이 중요합니다. 발표일 이후 현장 상황에 따라 점검 대상이나 일정이 달라질 수 있으므로, 실제 방문이나 신청이 필요한 사안은 담당 기관의 최신 공지를 기준으로 판단해야 합니다. 원문에는 발표 기관, 대상 지역, 일정, 현장 조치 방향이 함께 들어 있어 후속 보도와 비교해 보기 좋습니다.

이번 자료를 읽을 때에는 단순히 점검을 한다는 문장보다 누가, 언제까지, 어느 범위를 확인하는지가 핵심입니다. 행정안전부가 총괄하고 지방자치단체와 관계기관이 현장 확인을 맡는 구조라면 실제 조치는 지역별 공지로 이어질 가능성이 있습니다. 따라서 전국 공통 발표와 내가 사는 지역의 세부 안내를 나눠 보는 것이 필요합니다.
"""
        release = MODULE.PressRelease(
            institution="행정안전부",
            title="여름철 재난안전 점검",
            date="2026-06-14",
            url="https://example.go.kr/press",
            body_text=body,
            article_ready=True,
        )

        final = MODULE.finalize_article_body(release)

        self.assertIn("전국 17개 시도", final)
        self.assertIn("## 원문", final)
        self.assertNotIn("무엇을 발표했나", final)

    def test_concrete_reader_checks_uses_source_context(self) -> None:
        release = MODULE.PressRelease(
            institution="재정경제부",
            title="소상공인 지원금 신청 접수",
            date="2026-06-14",
            url="https://example.go.kr/press",
            body_text="소상공인 지원금 신청은 7월 1일부터 접수한다. 대상은 피해 소상공인 3만 명이다.",
        )

        checks = MODULE.concrete_reader_checks(release, ["피해 소상공인 3만 명"], [])

        self.assertIn("신청", checks)
        self.assertIn("지원", checks)
        self.assertNotIn("내 상황과 맞는지", checks)


if __name__ == "__main__":
    unittest.main()
