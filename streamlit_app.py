import json
import os
import boto3
import streamlit as st


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
if not st.user.is_logged_in:
    st.title("Bitte anmelden")
    if st.button("Login mit AWS Cognito"):
        st.login("cognito")  # Verweist auf den Block [auth.cognito] in den Secrets
    st.stop()

# Nach erfolgreichem Login:
st.sidebar.write(f"Eingeloggt als: {st.user.email}")
if st.button("Logout"):
    st.session_state.clear() # Clear all session data
    st.session_state.page = "login" # Set the page to ‘login’ after logout
 # Clear the sidebar and hide it
    st.sidebar.empty()  # Empty the sidebar to hide it
    st.write("You have been logged out.")

    # Rerun the app and go to the login page
    st.rerun()  # # Rerun the app to reset the session state
    
st.title("🤖 AWS AgentCore Runtime + Streamlit")
st.write("Stelle eine Frage an deinen Agenten:")

# Initialisiere den Bedrock-AgentCore-Client (oder den entsprechenden boto3-Client)
@st.cache_resource
def get_client():
    return boto3.client("bedrock-agentcore", region_name=AWS_REGION)

client = get_client()

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

    # Antwort vom AgentCore abrufen
    with st.chat_message("assistant"):
        with st.spinner("Agent arbeitet..."):
            try:
                # Beispiel-Aufruf (anhand der AWS-Schnittstelle für AgentCore Runtime)
                # Je nach Konfiguration wird hier Invoke / Payload übergeben
                response = client.invoke_agent_runtime(
                    agentRuntimeArn=AGENT_RUNTIME_ARN,
                    payload=json.dumps({"prompt": user_input}).encode("utf-8"),
                    contentType="application/json",
                )
                
                # Bedrock AgentCore liefert das Streaming-Body unter dem Schlüssel 'response'.
                agent_output = _extract_runtime_text(response)
                
            except Exception as e:
                agent_output = f"Fehler bei der Verbindung zur AgentCore Runtime: {e}"

            st.markdown(agent_output)
            st.session_state.messages.append({"role": "assistant", "content": agent_output})