import base64
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs

import requests
from authlib.integrations.requests_client import OAuth2Session

from agentcore_client import AgentCoreClient


class AgentCoreClientTests(unittest.TestCase):
    def setUp(self):
        self.client = AgentCoreClient(
            region="eu-central-1",
            runtime_arn="arn:aws:bedrock-agentcore:eu-central-1:123456789012:runtime/test",
            token_endpoint="https://example.auth.eu-central-1.amazoncognito.com/oauth2/token",
            client_id="test-client", client_secret="test-secret",
            scope="agent/invoke",
        )
        self.oauth_patch = patch("agentcore_client.OAuth2Session")
        self.oauth = self.oauth_patch.start()
        self.addCleanup(self.oauth_patch.stop)
        self.fetch_token = self.oauth.return_value.__enter__.return_value.fetch_token
        self.fetch_token.return_value = {
            "access_token": "test.jwt.token", "token_type": "Bearer", "expires_in": 3600,
        }

    def test_client_credentials_and_cached_token(self):
        with patch("agentcore_client.time.monotonic", return_value=100):
            self.assertEqual(self.client._get_access_token(), "test.jwt.token")
            self.assertEqual(self.client._get_access_token(), "test.jwt.token")
        self.oauth.assert_called_once_with(
            client_id="test-client", client_secret="test-secret", scope="agent/invoke",
            token_endpoint_auth_method="client_secret_basic",
        )
        self.fetch_token.assert_called_once_with(
            self.client.token_endpoint, grant_type="client_credentials", timeout=30,
            allow_redirects=False,
        )

    def test_authlib_sends_basic_auth_and_form_encoded_grant(self):
        response = requests.Response()
        response.status_code = 200
        response._content = (
            b'{"access_token":"jwt","token_type":"Bearer","expires_in":3600}'
        )
        with (
            patch("agentcore_client.OAuth2Session", OAuth2Session),
            patch("requests.sessions.Session.send", return_value=response) as send,
        ):
            self.assertEqual(self.client._get_access_token(), "jwt")
        request = send.call_args.args[0]
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, self.client.token_endpoint)
        credentials = base64.b64encode(b"test-client:test-secret").decode("ascii")
        self.assertEqual(request.headers["Authorization"], f"Basic {credentials}")
        self.assertEqual(
            request.headers["Content-Type"].split(";", 1)[0],
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(parse_qs(request.body), {
            "grant_type": ["client_credentials"], "scope": ["agent/invoke"],
        })

    def test_token_is_renewed_before_expiry(self):
        with patch("agentcore_client.time.monotonic", return_value=100):
            self.client._get_access_token()
        with patch("agentcore_client.time.monotonic", return_value=3640):
            self.client._get_access_token()
        self.assertEqual(self.fetch_token.call_count, 2)

    def test_invalid_token_is_not_cached(self):
        for token in (
            {},
            {"access_token": "token", "token_type": "Basic", "expires_in": 3600},
            {"access_token": "token", "token_type": "Bearer", "expires_in": 0},
        ):
            with self.subTest(token=token):
                self.fetch_token.return_value = token
                with self.assertRaises(ValueError):
                    self.client._get_access_token()
                self.assertIsNone(self.client._access_token)

    @patch("agentcore_client.requests.post")
    def test_runtime_uses_bearer_and_existing_payload(self, post):
        response = post.return_value.__enter__.return_value
        response.status_code = 200
        response.content = b'data: {"event": {}}\n'
        payload = b'{"prompt": "Hallo", "actorId": "user-sub"}'
        result = self.client.invoke_agent_runtime(
            runtime_session_id="session-id", payload=payload,
        )
        self.assertEqual(result["response"].read(), response.content)
        url = post.call_args.args[0]
        self.assertIn("arn%3Aaws%3Abedrock-agentcore%3A", url)
        self.assertIn("%3Aruntime%2Ftest/invocations?qualifier=DEFAULT", url)
        options = post.call_args.kwargs
        self.assertEqual(options["headers"]["Authorization"], "Bearer test.jwt.token")
        self.assertEqual(
            options["headers"]["X-Amzn-Bedrock-AgentCore-Runtime-Session-Id"],
            "session-id",
        )
        self.assertNotIn("X-Amzn-Bedrock-AgentCore-Runtime-User-Id", options["headers"])
        self.assertEqual(options["data"], payload)
        self.assertFalse(options["allow_redirects"])

    @patch("agentcore_client.requests.post")
    def test_runtime_http_errors_are_propagated(self, post):
        response = post.return_value.__enter__.return_value
        response.raise_for_status.side_effect = requests.HTTPError("401 Unauthorized")
        with self.assertRaises(requests.HTTPError):
            self.client.invoke_agent_runtime(runtime_session_id="session", payload=b"{}")

    def test_insecure_token_endpoint_is_rejected(self):
        with self.assertRaises(ValueError):
            AgentCoreClient(
                region="eu-central-1", runtime_arn="test",
                token_endpoint="http://example.com/oauth2/token",
                client_id="test", client_secret="secret", scope="agent/invoke",
            )


if __name__ == "__main__":
    unittest.main()