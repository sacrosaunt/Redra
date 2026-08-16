from __future__ import annotations

import json
from pathlib import Path

from scripts.export_mcp_contract import contract


def test_public_mcp_v2_contract_is_unchanged():
    expected = json.loads(
        (Path(__file__).parents[1] / "contracts" / "mcp-tools-v2.json").read_text(
            encoding="utf-8"
        )
    )

    assert contract() == expected
