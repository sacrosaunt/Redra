from __future__ import annotations

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock

from redra_mcp.server import create_mcp


def contract() -> dict:
    tools = create_mcp(service=MagicMock())._tool_manager.list_tools()
    return {
        "schema": "redra-mcp-tool-contract/v1",
        "compatibility": (
            "Tool removals, renames, parameter removals, type changes, or tighter "
            "bounds require a reviewed contract version. Additive optional fields "
            "may be released within v1 after client regression testing."
        ),
        "tools": [
            {
                "name": tool.name,
                "title": tool.title,
                "description": tool.description,
                "inputSchema": tool.parameters,
                "annotations": tool.annotations.model_dump(
                    mode="json", by_alias=True, exclude_none=True
                ) if tool.annotations else None,
            }
            for tool in tools
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Redra's frozen MCP v1 contract")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(contract(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
