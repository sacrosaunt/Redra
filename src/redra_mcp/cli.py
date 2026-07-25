from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence

from redra_mcp.config import Settings
from redra_mcp.dataset import DatasetImportError, update_dataset
from redra_mcp.http import (
    ConcurrencyLimitMiddleware,
    IPRateLimitMiddleware,
    RequestBodyLimitMiddleware,
)
from redra_mcp.providers.sqlite import SQLiteProvider
from redra_mcp.server import create_mcp


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="redra-mcp", description="Search settlement data through MCP"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve = subparsers.add_parser("serve", help="run the MCP server")
    serve.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default="stdio",
    )

    dataset = subparsers.add_parser("dataset", help="manage the local dataset")
    dataset_commands = dataset.add_subparsers(dest="dataset_command", required=True)
    dataset_commands.add_parser("update", help="download and index the latest dataset")
    dataset_commands.add_parser("info", help="show local dataset metadata")
    watch = dataset_commands.add_parser(
        "watch", help="keep the local dataset updated on an interval"
    )
    watch.add_argument("--interval-hours", type=float, default=24.0)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        if args.command == "serve":
            server = create_mcp(settings)
            if args.transport == "streamable-http":
                import uvicorn

                app = ConcurrencyLimitMiddleware(
                    server.streamable_http_app(),
                    limit=settings.max_concurrent_requests,
                )
                app = IPRateLimitMiddleware(
                    app,
                    limit=settings.rate_limit_per_hour,
                    trust_fly_headers=settings.trust_fly_headers,
                )
                app = RequestBodyLimitMiddleware(
                    app,
                    max_bytes=settings.max_request_body_bytes,
                )
                uvicorn.run(app, host=settings.host, port=settings.port)
            else:
                server.run(transport="stdio")
            return 0

        if args.dataset_command == "update":
            count = update_dataset(
                settings.database_path,
                settings.settlesignal_url,
                timeout=settings.request_timeout,
            )
            print(
                json.dumps(
                    {"updated": True, "record_count": count, "path": str(settings.database_path)}
                )
            )
            return 0

        if args.dataset_command == "watch":
            if args.interval_hours <= 0:
                raise ValueError("--interval-hours must be greater than zero")
            try:
                while True:
                    delay_hours = args.interval_hours
                    try:
                        count = update_dataset(
                            settings.database_path,
                            settings.settlesignal_url,
                            timeout=settings.request_timeout,
                        )
                        print(
                            json.dumps(
                                {
                                    "updated": True,
                                    "record_count": count,
                                    "path": str(settings.database_path),
                                }
                            ),
                            flush=True,
                        )
                    except DatasetImportError as exc:
                        delay_hours = min(1.0, args.interval_hours)
                        print(
                            f"dataset update failed: {exc}",
                            file=sys.stderr,
                            flush=True,
                        )
                    time.sleep(delay_hours * 3600)
            except KeyboardInterrupt:
                return 0

        provider = SQLiteProvider(settings.database_path)
        try:
            print(provider.info().model_dump_json(indent=2))
        finally:
            provider.close()
        return 0
    except (DatasetImportError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
