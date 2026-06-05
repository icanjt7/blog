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


if __name__ == "__main__":
    unittest.main()
