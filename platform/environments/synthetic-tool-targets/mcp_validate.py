from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def _payload(result: Any) -> dict[str, Any]:
    structured = getattr(result, "structuredContent", None)
    if isinstance(structured, dict):
        # FastMCP may wrap a returned mapping under result.
        if isinstance(structured.get("result"), dict):
            return structured["result"]
        return structured
    for item in getattr(result, "content", []):
        text = getattr(item, "text", None)
        if not isinstance(text, str):
            continue
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise RuntimeError("MCP tool did not return a mapping payload")


async def main() -> None:
    server = StdioServerParameters(
        command="mcp-server",
        args=["--server", "http://127.0.0.1:5000", "--timeout", "120"],
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {tool.name for tool in (await session.list_tools()).tools}
            required = {"sqlmap_scan", "hydra_attack", "enum4linux_scan"}
            missing = required - tools
            if missing:
                raise RuntimeError("missing MCP tools: " + ",".join(sorted(missing)))

            sqlmap = _payload(
                await session.call_tool(
                    "sqlmap_scan",
                    arguments={
                        "url": "http://synthetic-web:8080/item?id=1",
                        "additional_args": "--level=1 --risk=1 --technique=B --dbms=SQLite --flush-session --threads=1 --timeout=5 --retries=0",
                    },
                )
            )
            sql_text = (str(sqlmap.get("stdout", "")) + str(sqlmap.get("stderr", ""))).lower()
            if not sqlmap.get("success") or "inject" not in sql_text:
                raise RuntimeError("sqlmap MCP control did not demonstrate synthetic injection")

            hydra = _payload(
                await session.call_tool(
                    "hydra_attack",
                    arguments={
                        "target": "synthetic-web",
                        "service": "http-post-form",
                        "username": "labuser",
                        "password": "labpass",
                        "additional_args": "'/login:user=^USER^&pass=^PASS^:F=invalid credentials' -s 8080",
                    },
                )
            )
            hydra_text = (str(hydra.get("stdout", "")) + str(hydra.get("stderr", ""))).lower()
            if not hydra.get("success") or "labuser" not in hydra_text or "labpass" not in hydra_text:
                raise RuntimeError("hydra MCP control did not recover the fixed synthetic credential")

            enum4linux = _payload(
                await session.call_tool(
                    "enum4linux_scan",
                    arguments={"target": "synthetic-smb", "additional_args": "-a"},
                )
            )
            enum_text = (str(enum4linux.get("stdout", "")) + str(enum4linux.get("stderr", ""))).lower()
            if not enum4linux.get("success") or not ({"controlled", "workgroup"} & set(enum_text.replace("[", " ").replace("]", " ").split())):
                if "controlled" not in enum_text and "workgroup" not in enum_text:
                    raise RuntimeError("enum4linux MCP control did not enumerate the synthetic Samba fixture")

            print(
                json.dumps(
                    {
                        "sqlmap_scan": "PASS_SYNTHETIC_MCP",
                        "hydra_attack": "PASS_SYNTHETIC_MCP",
                        "enum4linux_scan": "PASS_SYNTHETIC_MCP",
                        "real_credentials": False,
                        "external_targets": False,
                    },
                    sort_keys=True,
                )
            )


if __name__ == "__main__":
    asyncio.run(main())
