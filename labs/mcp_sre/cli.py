"""
互動式示範 / Interactive demo.

    python -m labs.mcp_sre.cli                       # 診斷 payment-gateway，修改前會詢問
    python -m labs.mcp_sre.cli --service order-processor
    python -m labs.mcp_sre.cli --stdio               # 以子行程啟動 server，走真正的 stdio transport
"""

from __future__ import annotations

import argparse
import json

from .client import InProcessTransport, MCPClient, ProposedChange, StdioTransport, diagnose


def ask_human(p: ProposedChange) -> bool:
    print("\n=== Approval required ===")
    print(f"tool:      {p.tool}")
    print(f"arguments: {json.dumps(p.arguments)}")
    print(f"reason:    {p.reason}")
    print(f"evidence:  {', '.join(p.evidence)}")
    return input("Apply this change? [y/N] ").strip().lower() == "y"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--service", default="payment-gateway")
    ap.add_argument("--stdio", action="store_true", help="run the server as a subprocess")
    args = ap.parse_args()

    transport = StdioTransport() if args.stdio else InProcessTransport()
    client = MCPClient(transport).connect()
    print(f"connected to {client.server_info['serverInfo']['name']} "
          f"(protocol {client.server_info['protocolVersion']})")
    for name, tool in client.tools.items():
        print(f"  - {name:26} read_only={client.is_read_only(name)}")

    d = diagnose(client, args.service, approve=ask_human)
    print("\n".join(["", "log:"] + [f"  {line}" for line in d.log]))
    if isinstance(transport, StdioTransport):
        transport.close()


if __name__ == "__main__":
    main()
