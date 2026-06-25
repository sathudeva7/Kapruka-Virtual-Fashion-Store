"""ADK web entrypoint.

`adk web` discovers each subfolder with an `agent.py` exposing `root_agent`.
This is a thin wrapper that reuses the existing root agent defined in the
project's `rootagent/` package — no agent logic is duplicated here.
"""
import sys
from pathlib import Path

# Make the project root importable regardless of how `adk web` is invoked
# (pointed at the project root OR directly at this agent folder).
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

# Single source of truth for the API key — the root .env.
load_dotenv(PROJECT_ROOT / ".env")

from rootagent.agent import ecommerce_agent

# The name `adk web` looks for.
root_agent = ecommerce_agent
