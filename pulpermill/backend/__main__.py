"""python -m pulpermill.backend --fake [--port 8000] [--token SECRET]
Runs the server with the fake engine, so the page can be tried against it with no GPU."""
import argparse
import logging

import uvicorn

from .config import Config
from .engine import FakeEngine
from .server import create_app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake", action="store_true", help="use the fake engine (the only one until M2)")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--token", default=None, help="the shared secret; or set PULPERMILL_TOKEN")
    parser.add_argument("--seconds-per-token", type=float, default=0.05)
    args = parser.parse_args()
    if not args.fake:
        parser.error("only --fake exists until the real engine is built")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    config = Config.from_env(host=args.host, port=args.port) if not args.token else Config(token=args.token, host=args.host, port=args.port)
    logging.getLogger("pulpermill").info("starting %s", config.describe())
    uvicorn.run(create_app(config, FakeEngine(seconds_per_token=args.seconds_per_token, tokens_per_call=20)),
                host=config.host, port=config.port, log_level="warning")


if __name__ == "__main__":
    main()
