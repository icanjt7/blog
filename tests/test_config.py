from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from blog_agent.config import DEFAULT_GA_MEASUREMENT_ID, Settings, load_settings


class SettingsTest(unittest.TestCase):
    def test_ga_measurement_id_defaults_to_site_tag(self) -> None:
        self.assertEqual(Settings().ga_measurement_id, DEFAULT_GA_MEASUREMENT_ID)

    def test_load_settings_uses_default_ga_tag_when_env_is_empty(self) -> None:
        with patch.dict(os.environ, {"GA_MEASUREMENT_ID": ""}, clear=True):
            settings = load_settings()

        self.assertEqual(settings.ga_measurement_id, DEFAULT_GA_MEASUREMENT_ID)


if __name__ == "__main__":
    unittest.main()
