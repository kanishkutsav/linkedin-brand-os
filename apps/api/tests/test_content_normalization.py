import unittest

from app.guards.guardrails import normalize_human_style, run_content_guards


class TestContentNormalization(unittest.TestCase):
    def test_literal_escaped_newlines_are_converted(self):
        raw = r"Opening line.\\n1) First item\\n2) Second item"
        normalized = normalize_human_style(raw)
        self.assertEqual(normalized, "Opening line.\n1. First item\n2. Second item")
        self.assertNotIn(r"\\n", normalized)

    def test_orphaned_number_marker_is_joined_to_item_text(self):
        normalized = normalize_human_style("A useful point:\n1.\nFirst item\n2.\nSecond item")
        self.assertEqual(normalized, "A useful point:\n1. First item\n2. Second item")

    def test_guards_reject_unprocessed_escape_sequences_and_orphan_markers(self):
        escaped = run_content_guards(r"This is a sufficiently long sentence for a post.\\nSecond line.")
        orphan = run_content_guards("This is a sufficiently long sentence for a post.\n1.")
        self.assertFalse(escaped.passed)
        self.assertTrue(any("Escaped newline" in issue for issue in escaped.issues))
        self.assertFalse(orphan.passed)
        self.assertTrue(any("Numbered list" in issue for issue in orphan.issues))


if __name__ == "__main__":
    unittest.main()
