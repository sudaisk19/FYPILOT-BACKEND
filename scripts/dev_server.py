#!/usr/bin/env python3
"""
Local dev server entrypoint — avoids a uvicorn.run(import_string) + default logging
path that can SIGSEGV on some Linux setups (fish + pyenv + uvicorn 0.35 observed).

Usage (from repo root, venv active):
  python scripts/dev_server.py

Reload (external): install watchfiles and run:
  watchfiles "python scripts/dev_server.py" ./app
"""
from __future__ import annotations

import os

from uvicorn import Config, Server


def main() -> None:
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    c = Config(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_config=None,
        loop="asyncio",
        http="h11",
        ws="websockets",
    )
    c.load()
    Server(c).run()


if __name__ == "__main__":
    main()
