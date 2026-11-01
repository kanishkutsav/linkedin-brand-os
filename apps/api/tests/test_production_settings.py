import unittest

from app.core.config import Settings


class TestProductionSettings(unittest.TestCase):
    def test_production_requires_non_default_secret(self):
        with self.assertRaisesRegex(ValueError, "SECRET_KEY"):
            Settings(environment="production", app_env="production")

    def test_vercel_production_is_recognized_and_accepts_strong_secrets(self):
        settings = Settings(vercel_env="production", secret_key="s" * 40, jwt_secret="j" * 40)
        self.assertTrue(settings.is_production)


if __name__ == "__main__":
    unittest.main()
