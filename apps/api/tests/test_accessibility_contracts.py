import json
import re
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


class TestAccessibilityContracts(unittest.TestCase):
    def test_global_keyboard_focus_and_reduced_motion_support_exist(self):
        stylesheet = (REPOSITORY_ROOT / "apps/web/app/globals.css").read_text(encoding="utf-8")
        self.assertIn(":focus-visible", stylesheet)
        self.assertIn("@media (prefers-reduced-motion: reduce)", stylesheet)



    def test_form_controls_have_programmatic_accessible_names(self):
        source = (REPOSITORY_ROOT / "apps/web/app/page.tsx").read_text(encoding="utf-8")
        controls = re.findall(r"<(?:input|textarea|select)\\b[\\s\\S]*?>", source)
        self.assertTrue(controls, "Expected form controls in the application.")
        for control in controls:
            self.assertRegex(control, r"\\baria-label\\s*=")

    def test_frontend_lockfile_matches_exact_package_manifest(self):
        package = json.loads((REPOSITORY_ROOT / "apps/web/package.json").read_text(encoding="utf-8"))
        lock = json.loads((REPOSITORY_ROOT / "apps/web/package-lock.json").read_text(encoding="utf-8"))
        self.assertEqual(lock["packages"][""]["dependencies"], package["dependencies"])
        self.assertEqual(lock["packages"][""]["devDependencies"], package["devDependencies"])

    def test_all_static_image_elements_have_alt_text(self):
        source = (REPOSITORY_ROOT / "apps/web/app/page.tsx").read_text(encoding="utf-8")
        image_elements = re.findall(r"<img\b[\s\S]*?>", source)
        self.assertTrue(image_elements, "Expected the application to contain image elements.")
        for image in image_elements:
            self.assertRegex(image, r"\balt\s*=")


if __name__ == "__main__":
    unittest.main()
