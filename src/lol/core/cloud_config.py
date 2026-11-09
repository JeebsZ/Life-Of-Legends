"""Cloud, Google OAuth & Store Update configuration for Life of Legends."""

from __future__ import annotations

import os

# App identity & Google Play Store info
APP_PACKAGE_ID = os.getenv("LUMA_PACKAGE_ID", "com.companions.LUMA")
APP_VERSION = os.getenv("LUMA_APP_VERSION", "0.2.2")
APP_BUILD_NUMBER = int(os.getenv("LUMA_BUILD_NUMBER", "19"))
PLAY_STORE_URL = os.getenv(
    "LUMA_PLAY_STORE_URL",
    f"https://play.google.com/store/apps/details?id={APP_PACKAGE_ID}",
)
VERSION_CHECK_URL = os.getenv("LUMA_VERSION_CHECK_URL", "")

# Default or environment-provided credentials
GOOGLE_CLIENT_ID = os.getenv(
    "LUMA_GOOGLE_CLIENT_ID",
    "724871304108-7p02bpjspjdeus6m08g0bantleuffih5.apps.googleusercontent.com",
)
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

# Developer Google accounts that automatically unlock Dev Mode on sign-in
DEV_EMAILS: frozenset[str] = frozenset(
    e.strip().lower()
    for e in os.getenv("LUMA_DEV_EMAILS", "jarvin.eslao.work@gmail.com").split(",")
    if e.strip()
)

# AdMob App ID & Production Rewarded Ad Units
ADMOB_APP_ID = os.getenv(
    "LUMA_ADMOB_APP_ID",
    "ca-app-pub-8988346601586726~XXXXXXXXXX",  # App settings -> App ID
)
ADMOB_REWARDED_UNITS: dict[str, str] = {
    "pre_run_stretch": os.getenv(
        "LUMA_AD_PRE_RUN", "ca-app-pub-8988346601586726/2504206889"
    ),
    "run_tracking": os.getenv(
        "LUMA_AD_RUN", "ca-app-pub-8988346601586726/1642551353"
    ),
    "meal_scan": os.getenv(
        "LUMA_AD_MEAL", "ca-app-pub-8988346601586726/7339545250"
    ),
    "workout_boost": os.getenv(
        "LUMA_AD_WORKOUT", "ca-app-pub-8988346601586726/1568343825"
    ),
    "focus_ambience": os.getenv(
        "LUMA_AD_FOCUS", "ca-app-pub-8988346601586726/6553077195"
    ),
    "quest_slot": os.getenv(
        "LUMA_AD_QUEST", "ca-app-pub-8988346601586726/2655203944"
    ),
    "bonus_reward": os.getenv(
        "LUMA_AD_BONUS", "ca-app-pub-8988346601586726/1302805852"
    ),
}



