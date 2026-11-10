import json
import uuid
import streamlit as st

from agentcore_client import AgentCoreClient


def _extract_runtime_text(response):
    """Read a Bedrock AgentCore runtime event stream and return the assistant text."""
    body = response.get("response")
    if body is None:
        raise KeyError("Missing 'response' in AgentCore runtime response")

    raw = body.read().decode("utf-8", errors="replace")
    if not raw.strip():
        return "Keine Antwort erhalten."

    parts = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            parts.append(payload)
            continue

        event_obj = event.get("event", {}) if isinstance(event, dict) else {}
        delta = event_obj.get("contentBlockDelta", {}).get("delta", {})
        if "text" in delta:
            parts.append(delta["text"])

    return "".join(parts) if parts else raw

# Konfiguration (kann auch über Umgebungsvariablen gesteuert werden)
AWS_REGION = st.secrets["AWS_REGION"]
AGENT_RUNTIME_ARN = st.secrets["AGENT_RUNTIME_ARN"]

# Prüfen, ob der Nutzer angemeldet ist
auth_config = st.secrets.get("auth", {})
if not auth_config or "cognito" not in auth_config:
    st.error(
        "Die Cognito-Benutzeranmeldung ist nicht konfiguriert. "
        "Ergänze [auth] und [auth.cognito] in .streamlit/secrets.toml "
        "(siehe README.md). [agentcore_m2m] authentifiziert nur die App "
        "gegenüber AgentCore und ersetzt keinen Benutzer-Login."
    )
    st.stop()

if not st.user.get("is_logged_in", False):
    st.title("Bitte anmelden")
    if st.button("Login mit AWS Cognito"):
        st.login("cognito")  # Verweist auf den Block [auth.cognito] in den Secrets
    st.stop()

# Nach erfolgreichem Login:
user_name = " ".join(
    part
    for part in (
        st.user.get("given_name"),
        st.user.get("family_name"),
    )
    if part
)

st.sidebar.write(f"Eingeloggt als: {user_name}")
if user_name == st.user.email:
    st.sidebar.caption(
        "Cognito hat keinen Namens-Claim übermittelt. Prüfe das Namensattribut "
        "und dessen Leseberechtigung im Cognito-App-Client."
    )
if st.button("Logout"):
    # Alle Schlüssel im session_state löschen
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    
    # Optional: Streamlit-eigenen Login-Status zurücksetzen
    st.logout()
    
    # Seite neu laden, um die Ansicht zu aktualisieren
    st.rerun()

st.title("🤖 AWS AgentCore Runtime")
st.write("Stelle eine Frage an deinen Agenten:")

actor_id = st.user.get("sub")
if not actor_id:
    st.error("Die Nutzer-ID (OIDC-Claim 'sub') fehlt.")
    st.stop()

if "runtime_session_id" not in st.session_state:
    st.session_state.runtime_session_id = str(uuid.uuid4())

def get_client():
    if "agentcore_client" not in st.session_state:
        st.session_state.agentcore_client = AgentCoreClient(
            region=AWS_REGION,
            runtime_arn=AGENT_RUNTIME_ARN,
            **dict(st.secrets["agentcore_m2m"]),
        )
    return st.session_state.agentcore_client

# Chat-Verlauf initialisieren
if "messages" not in st.session_state:
    st.session_state.messages = []

# Bisherigen Chatverlauf anzeigen
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Benutzereingabe
if user_input := st.chat_input("Was möchtest du tun?"):
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    agent_prompt = (
        f"Der angemeldete Nutzer heißt {user_name}. "
        f"Sprich ihn bei Bedarf mit seinem Namen an.\n\n{user_input}"
    )

    # Antwort vom AgentCore abrufen
    with st.chat_message("assistant"):
        with st.spinner("Agent arbeitet..."):
            try:
                response = get_client().invoke_agent_runtime(
                    runtime_session_id=st.session_state.runtime_session_id,
                    payload=json.dumps(
                        {
                            "prompt": agent_prompt,
                            "actorId": actor_id,
                            "userName": user_name,
                        }
                    ).encode("utf-8"),
                )
                
                # Bedrock AgentCore liefert das Streaming-Body unter dem Schlüssel 'response'.
                agent_output = _extract_runtime_text(response)
                
            except Exception as e:
                agent_output = f"Fehler bei der Verbindung zur AgentCore Runtime: {e}"

            st.markdown(agent_output)
            st.session_state.messages.append({"role": "assistant", "content": agent_output})