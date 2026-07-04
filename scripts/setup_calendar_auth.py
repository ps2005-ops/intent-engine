"""One-time interactive OAuth setup for real Google Calendar access (read-only).

Run this ONCE, manually, from a terminal with a real browser available:

    python scripts/setup_calendar_auth.py

This is a manual, interactive step -- NOT something tests can or should
automate. It opens a real browser window, asks you to log into Google, and
asks you to approve read-only Calendar access for this app. Every subsequent
GoogleCalendarReader.read_events() call reuses the resulting token silently
(refreshing it automatically as needed); you should only need to run this
script again if the token is revoked, deleted, or the app credentials change.

Before running this script:
1. In Google Cloud Console, create (or use) a project with the Calendar API
   enabled.
2. Under APIs & Services > Credentials, create an OAuth client ID of type
   "Desktop app" (not "Web application" -- Desktop avoids needing a public
   HTTPS redirect URI, which this local-dev setup doesn't have).
3. Download the client credentials JSON and save it to
   credentials/client_secret.json (exact path -- see
   voice/calendar.py's DEFAULT_CLIENT_SECRET_PATH). Both this file and the
   resulting data/calendar_token.json are gitignored -- never commit either.
"""

import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from intent_engine.voice.calendar import (
    CALENDAR_READONLY_SCOPES,
    DEFAULT_CALENDAR_TOKEN_PATH,
    DEFAULT_CLIENT_SECRET_PATH,
)


def main() -> int:
    if not DEFAULT_CLIENT_SECRET_PATH.exists():
        print(
            f"Missing {DEFAULT_CLIENT_SECRET_PATH}. Download it from Google Cloud "
            "Console (APIs & Services > Credentials > OAuth client ID > Desktop app) "
            "and save it to that exact path before running this script.",
            file=sys.stderr,
        )
        return 1

    flow = InstalledAppFlow.from_client_secrets_file(str(DEFAULT_CLIENT_SECRET_PATH), CALENDAR_READONLY_SCOPES)
    creds = flow.run_local_server(port=0)

    DEFAULT_CALENDAR_TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    DEFAULT_CALENDAR_TOKEN_PATH.write_text(creds.to_json())
    print(f"Saved Calendar credentials to {DEFAULT_CALENDAR_TOKEN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
