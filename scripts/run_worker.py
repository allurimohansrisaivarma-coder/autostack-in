"""Spike worker launcher: starts uvicorn + the in-process trigger loop (B3).

Token precedence is handled by backend.spike_config: env AUTOSTACK_TOKEN wins,
otherwise the persisted artifacts/spike/token is reused (or created). No hardcoded
default credential is injected here.
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import uvicorn  # noqa: E402

from backend.app import app  # noqa: E402
from backend.roadmap_routes import start_trigger_loop_if_needed  # noqa: E402

start_trigger_loop_if_needed()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8747, log_level="info")
