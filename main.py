"""FastAPI entrypoint — `uvicorn main:app` (see run.sh / Dockerfile).

All server code lives in the `server/` package. This module only loads the
environment and builds the app: `load_dotenv()` MUST run before `server` is
imported, because importing the routers pulls in the agent packages, which
read GOOGLE_API_KEY (and friends) at import time.
"""

from dotenv import load_dotenv

load_dotenv()

from server.app import create_app  # noqa: E402  (import after dotenv on purpose)

app = create_app()
