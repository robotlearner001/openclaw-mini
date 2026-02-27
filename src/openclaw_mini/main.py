from __future__ import annotations

import logging
import sys

from .bot import build_discord_client
from .config import load_settings


def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        settings = load_settings()
    except Exception as exc:  # noqa: BLE001
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

    client = build_discord_client(settings)
    client.run(settings.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    run()
