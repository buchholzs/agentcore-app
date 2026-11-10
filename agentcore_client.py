import io
import time
from urllib.parse import quote, urlsplit

import requests
from authlib.integrations.requests_client import OAuth2Session


class AgentCoreClient:
    def __init__(
        self, *, region, runtime_arn, token_endpoint, client_id, client_secret,
        scope, qualifier="DEFAULT",
    ):
        endpoint = urlsplit(token_endpoint)
        if endpoint.scheme != "https" or not endpoint.hostname:
            raise ValueError("Der Cognito-Token-Endpunkt muss eine HTTPS-URL sein.")
        self.url = (
            f"https://bedrock-agentcore.{region}.amazonaws.com/runtimes/"
            f"{quote(runtime_arn, safe='')}/invocations?"
            f"qualifier={quote(qualifier, safe='')}"
        )
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self._access_token = None
        self._expires_at = 0

    def _get_access_token(self):
        if self._access_token and time.monotonic() < self._expires_at:
            return self._access_token

        started_at = time.monotonic()
        with OAuth2Session(
            client_id=self.client_id,
            client_secret=self.client_secret,
            scope=self.scope,
            token_endpoint_auth_method="client_secret_basic",
        ) as oauth:
            token = oauth.fetch_token(
                self.token_endpoint, grant_type="client_credentials", timeout=30,
                allow_redirects=False,
            )
        access_token = token.get("access_token")
        expires_in = float(token.get("expires_in", 0))
        if (
            not isinstance(access_token, str) or not access_token
            or token.get("token_type", "").lower() != "bearer"
            or expires_in <= 0
        ):
            raise ValueError("Cognito hat kein gueltiges Bearer-Access-Token geliefert.")
        self._access_token = access_token
        self._expires_at = started_at + max(0, expires_in - 60)
        return self._access_token

    def invoke_agent_runtime(self, *, runtime_session_id, payload):
        with requests.post(
            self.url,
            headers={
                "Authorization": f"Bearer {self._get_access_token()}",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "X-Amzn-Bedrock-AgentCore-Runtime-Session-Id": runtime_session_id,
            },
            data=payload,
            timeout=(10, 300),
            allow_redirects=False,
        ) as response:
            response.raise_for_status()
            if response.status_code != 200:
                raise RuntimeError(f"AgentCore HTTP-Status: {response.status_code}")
            return {"response": io.BytesIO(response.content)}