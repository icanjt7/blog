"""
Run this locally (not in headless CI) to obtain a refresh token for Blogger.
Requires: `pip install google-auth-oauthlib`

Set env vars or replace the placeholders with your OAuth client ID/secret.

This script will open a browser to let you authorize and then print a refresh token.
"""
import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

CLIENT_ID = os.getenv("BLOGGER_OAUTH_CLIENT_ID")
CLIENT_SECRET = os.getenv("BLOGGER_OAUTH_CLIENT_SECRET")
SCOPES = ["https://www.googleapis.com/auth/blogger"]

if not CLIENT_ID or not CLIENT_SECRET:
    print("Please set BLOGGER_OAUTH_CLIENT_ID and BLOGGER_OAUTH_CLIENT_SECRET in your environment.")
    raise SystemExit(1)

client_config = {
    "installed": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
creds = flow.run_local_server(port=0)

print("Refresh token (store in BLOGGER_REFRESH_TOKEN):\n")
print(creds.refresh_token)

# Optionally write to a .env snippet
print('\nAdd the following to your .env file:')
print(f'BLOGGER_OAUTH_CLIENT_ID={CLIENT_ID}')
print(f'BLOGGER_OAUTH_CLIENT_SECRET={CLIENT_SECRET}')
print(f'BLOGGER_REFRESH_TOKEN={creds.refresh_token}')
