#!/usr/bin/env python
"""
Subscribe to the '/api/status' websocket of ophyd-service and print the status messages.

Usage:
    python status_monitor.py [--url ws://localhost:8000/api/status] [--json]


pixi run python status_monitor.py
pixi run python status_monitor.py --json
pixi run python status_monitor.py --url ws://some-host:8000/api/status
"""

import argparse
import asyncio
import contextlib
import json

import websockets

RECONNECT_DELAY = 2.0


def format_status(status):
    return (
        f"{status.get('time', '')[11:23]:<12} "
        f"manager={str(status.get('manager_state')):<8} "
        f"env_exists={str(status.get('worker_environment_exists')):<5} "
        f"worker={str(status.get('worker_environment_state')):<10} "
        f"uid={str(status.get('status_uid'))[:8]}"
    )


async def monitor(url, as_json):
    while True:
        try:
            async with websockets.connect(url) as ws:
                print(f"Connected to {url}")
                async for message in ws:
                    status = json.loads(message).get("status", {})
                    if as_json:
                        print(json.dumps(status, indent=2))
                    else:
                        print(format_status(status))
        except (OSError, websockets.exceptions.WebSocketException) as ex:
            # The server may be down or restarting: keep trying to reconnect.
            print(f"Connection failed or closed ({type(ex).__name__}: {ex}). Retrying ...")

        await asyncio.sleep(RECONNECT_DELAY)


def main():
    parser = argparse.ArgumentParser(description="Monitor the status stream of ophyd-service.")
    parser.add_argument("--url", default="ws://localhost:60620/api/status", help="Websocket URL.")
    parser.add_argument(
        "--json", action="store_true", default=True, help="Print the full status as formatted JSON."
    )
    args = parser.parse_args()

    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(monitor(args.url, args.json))


if __name__ == "__main__":
    main()
