import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


class LoginTests(unittest.TestCase):
    def make_app(self):
        app = AppTest.from_file(str(Path(__file__).with_name("streamlit_app.py")))
        # Replace local secrets completely; never use real credentials in tests.
        app.secrets = {
            "AWS_REGION": "eu-central-1",
            "AGENT_RUNTIME_ARN": "test-runtime",
            "agentcore_m2m": {
                "token_endpoint": "https://example.invalid/oauth2/token",
                "client_id": "test-m2m-client",
                "client_secret": "test-m2m-secret",
                "scope": "agentcore/invoke",
            },
        }
        return app

    def test_missing_auth_stops_with_configuration_message(self):
        app = self.make_app().run()
        self.assertFalse(app.exception)
        self.assertIn("[auth.cognito]", app.error[0].value)
        self.assertEqual(len(app.chat_input), 0)
        self.assertEqual(len(app.button), 0)

    def test_missing_cognito_provider_stops_safely(self):
        app = self.make_app()
        app.secrets["auth"] = {"cookie_secret": "test-cookie-secret"}
        app.run()
        self.assertFalse(app.exception)
        self.assertIn("[auth.cognito]", app.error[0].value)
        self.assertEqual(len(app.chat_input), 0)

    def test_configured_auth_shows_login_without_mocking_user(self):
        app = self.make_app()
        app.secrets["auth"] = {
            "redirect_uri": "http://localhost:8501/oauth2callback",
            "cookie_secret": "test-cookie-secret",
            "cognito": {
                "client_id": "test-login-client",
                "client_secret": "test-login-secret",
                "server_metadata_url": "https://example.invalid/.well-known/openid-configuration",
            },
        }
        app.run()
        self.assertFalse(app.exception)
        self.assertEqual(len(app.error), 0)
        self.assertEqual(app.title[0].value, "Bitte anmelden")
        self.assertEqual(app.button[0].label, "Login mit AWS Cognito")
        self.assertEqual(len(app.chat_input), 0)


if __name__ == "__main__":
    unittest.main()