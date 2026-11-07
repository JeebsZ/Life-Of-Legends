"""Cloud & Google OAuth configuration for Life of Legends."""

from __future__ import annotations

import os

# Default or environment-provided credentials
GOOGLE_CLIENT_ID = os.getenv("LUMA_GOOGLE_CLIENT_ID", "724871304108-7p02bpjspjdeus6m08g0bantleuffih5.apps.googleusercontent.com")
GOOGLE_CLIENT_SECRET = os.getenv("LUMA_GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URL = os.getenv(
    "LUMA_GOOGLE_REDIRECT_URL", "http://localhost:8550/oauth_callback"
)

# Drive AppData scope allows read/write to the app's hidden storage only
DRIVE_SCOPES = [
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/drive.appdata",
]

