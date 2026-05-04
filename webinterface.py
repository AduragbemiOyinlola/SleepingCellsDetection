import streamlit as st
import msal
import requests
import base64

CLIENT_ID = "your-client-id"
TENANT_ID = "your-tenant-id"

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES = ["Mail.Read"]

def authenticate():
    app = msal.PublicClientApplication(CLIENT_ID, authority=AUTHORITY)

    flow = app.initiate_device_flow(scopes=SCOPES)

    if "user_code" not in flow:
        raise Exception("Failed to create device flow")

    st.write("### Login Required")
    st.write(flow["message"])  # shows code + link

    result = app.acquire_token_by_device_flow(flow)

    if "access_token" in result:
        return result["access_token"]
    else:
        st.error("Authentication failed")
        return None


def fetch_csv(token):
    headers = {"Authorization": f"Bearer {token}"}

    url = (
        "https://graph.microsoft.com/v1.0/me/messages"
        "?$filter=subject eq 'sleeping cells'"
        "&$orderby=receivedDateTime desc"
        "&$top=1"
    )

    res = requests.get(url, headers=headers).json()

    if not res.get("value"):
        st.warning("No email found")
        return

    msg_id = res["value"][0]["id"]

    att_url = f"https://graph.microsoft.com/v1.0/me/messages/{msg_id}/attachments"
    att_res = requests.get(att_url, headers=headers).json()

    for att in att_res["value"]:
        if att["name"].endswith(".csv"):
            file_bytes = base64.b64decode(att["contentBytes"])

            st.download_button(
                label="Download CSV",
                data=file_bytes,
                file_name=att["name"],
                mime="text/csv"
            )
            return

    st.warning("No CSV attachment found")


# =====================
# STREAMLIT UI
# =====================
st.title("Email CSV Fetcher")

if st.button("Login to Outlook"):
    token = authenticate()
    if token:
        st.session_state["token"] = token

if "token" in st.session_state:
    if st.button("Fetch Latest CSV"):
        fetch_csv(st.session_state["token"])