# MCP compatibility contract

`mcp-tools-v2.json` is the current reviewer-tested public tool surface. CI compares the
live FastMCP definitions byte-for-byte with this snapshot.

Removing or renaming a tool or parameter, changing a parameter type, or
tightening a bound requires a new reviewed contract version. Additive optional
fields may remain in v2 only after the ChatGPT, Claude, and generic MCP fixtures
continue to pass.

Regenerate intentionally with:

```bash
PYTHONPATH=src python scripts/export_mcp_contract.py contracts/mcp-tools-v2.json
```
