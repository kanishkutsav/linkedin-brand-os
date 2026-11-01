import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class TestAccessibilityContracts(unittest.TestCase):
    def test_global_keyboard_focus_and_reduced_motion_support_exist(self):
        stylesheet = (REPOSITORY_ROOT / "apps/web/app/globals.css").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)

    def test_all_static_image_elements_have_alt_text(self):
        source = (REPOSITORY_ROOT / "apps/web/app/page.tsx").read_text(encoding="utf-8")
        image_elements = re.findall(r"<img\b[\s\S]*?>", source)
        self.assertTrue(image_elements, "Expected the application to contain image elements.")
        for image in image_elements:
            self.assertRegex(image, r"\balt\s*=")


if __name__ == "__main__":
    unittest.main()
