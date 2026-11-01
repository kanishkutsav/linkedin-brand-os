import unittest

from app.agents.research import _is_public_remote_address


class TestResearchFetchSSRF(unittest.TestCase):
    def test_actual_remote_peer_must_be_public(self):
        self.assertTrue(_is_public_remote_address(("8.8.8.8", 443)))
        self.assertTrue(_is_public_remote_address(("2606:4700:4700::1111", 443, 0, 0)))
        self.assertFalse(_is_public_remote_address(("127.0.0.1", 80)))
        self.assertFalse(_is_public_remote_address(("169.254.169.254", 80)))
        self.assertFalse(_is_public_remote_address(("::1", 80, 0, 0)))
        self.assertFalse(_is_public_remote_address(None))
        self.assertFalse(_is_public_remote_address("8.8.8.8"))


if __name__ == "__main__":
    unittest.main()
