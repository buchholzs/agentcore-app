# 🎈 AgentCore Streamlit App

Eine einfache Streamlit App zum Chatten mit einem AgentCore Agenten.

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://blank-app-template.streamlit.app/)

### How to run it on your own machine

Prerequisite: install `uv` if you don't already have it.

```
$ curl -LsSf https://astral.sh/uv/install.sh | sh
```

1. Sync the dependencies

   ```
   $ uv sync
   ```

2. Run the app

   ```
   $ uv run streamlit run streamlit_app.py
   ```

### AgentCore mit Cognito-M2M-JWT aufrufen

Der Benutzer-Login ueber `[auth.cognito]` bleibt bestehen. Fuer die Verbindung
zwischen App und AgentCore wird ein separater Cognito-App-Client mit Client-Secret,
OAuth-Flow `client_credentials` und einem freigegebenen Custom-Scope benoetigt.
Der Login-Client und der M2M-Client sind unterschiedliche App-Clients.

Ergaenze die Streamlit-Secrets (lokal in `.streamlit/secrets.toml`, niemals committen):

```toml
AWS_REGION = "eu-central-1"
AGENT_RUNTIME_ARN = "arn:aws:bedrock-agentcore:eu-central-1:123456789012:runtime/AGENT_ID"

[agentcore_m2m]
token_endpoint = "https://YOUR_DOMAIN.auth.eu-central-1.amazoncognito.com/oauth2/token"
client_id = "YOUR_M2M_CLIENT_ID"
client_secret = "YOUR_M2M_CLIENT_SECRET"
scope = "agentcore/invoke"
qualifier = "DEFAULT"

[auth]
redirect_uri = "http://localhost:8501/oauth2callback"
cookie_secret = "REPLACE_WITH_A_RANDOM_SECRET"

[auth.cognito]
client_id = "YOUR_LOGIN_CLIENT_ID"
client_secret = "YOUR_LOGIN_CLIENT_SECRET"
server_metadata_url = "https://cognito-idp.eu-central-1.amazonaws.com/YOUR_USER_POOL_ID/.well-known/openid-configuration"
client_kwargs = { scope = "openid email profile" }
```

Der separate Login-App-Client muss den Authorization-Code-Flow und die oben
angegebene Callback-URL erlauben. Fuer bereitgestellte Apps ist eine passende
HTTPS-Callback-URL zu verwenden. `cookie_secret` muss ein eigener, zufaelliger
geheimer Wert sein. M2M-Zugangsdaten ersetzen diese Benutzer-Login-Konfiguration
nicht. Ohne `[auth]` stellt Streamlit `st.user.is_logged_in` nicht bereit; die
App zeigt dann einen Konfigurationshinweis und gibt den Chat nicht frei.

`scope` muss einem fuer den M2M-Client erlaubten Resource-Server-Scope entsprechen;
mehrere Scopes werden durch Leerzeichen getrennt. Das Access-Token wird nur
serverseitig pro Streamlit-Sitzung gehalten und 60 Sekunden vor Ablauf erneuert.
Beim Logout wird es zusammen mit dem Sitzungszustand entfernt.

Die aufgerufene AgentCore-Runtime-Version muss einen `customJWTAuthorizer`
verwenden (statt IAM/SigV4), mit folgender Konfiguration:

```json
{
   "customJWTAuthorizer": {
      "discoveryUrl": "https://cognito-idp.eu-central-1.amazonaws.com/YOUR_USER_POOL_ID/.well-known/openid-configuration",
      "allowedClients": ["YOUR_M2M_CLIENT_ID"]
   }
}
```

Der Authorizer prueft Signatur, Issuer, Ablauf und erlaubten Client des JWTs.
Falls zusaetzlich Scopes oder Audience eingeschraenkt sind, muessen diese zum
ausgestellten M2M-Token passen. Cognito-M2M-Tokens haben standardmaessig keinen
`aud`-Claim. Fuer den Aufruf werden keine AWS-Zugangsdaten benoetigt.

Das JWT authentifiziert die App, nicht den eingeloggten Benutzer. `actorId` und
`userName` bleiben Anwendungskontext im Payload; sie sind keine durch das
M2M-Token bestaetigte Benutzeridentitaet und ersetzen keine Benutzerautorisierung.
Der IAM-spezifische Runtime-User-Id-Header wird deshalb nicht mehr gesendet.

Tests ohne echte Cognito- oder AgentCore-Aufrufe:

```sh
uv run python -m unittest -v test_agentcore_client test_streamlit_app
```
