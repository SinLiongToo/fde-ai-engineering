"""
MCP client 與 SRE 診斷流程 / MCP client and an SRE diagnosis workflow.

兩種 transport / Two transports
- InProcessTransport：直接呼叫 server 物件，方便測試。
- StdioTransport：把 server 當子行程啟動，透過 stdin/stdout 傳 JSON-RPC，和真實 MCP host 一樣。

診斷流程刻意寫成「workflow」而不是自主 agent：步驟固定、由程式控制，
只有「要不要改設定」交給人決定。多數維運情境，這比讓模型自由發揮更安全、更好除錯。
The diagnosis is a fixed workflow, not a free-roaming agent. Code decides the steps;
a human decides whether to change production.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

from .protocol import SUPPORTED_PROTOCOL_VERSIONS, CallToolResult, JSONRPCRequest
from .server import SREServer


class Transport(Protocol):
    def send(self, message: dict) -> dict | None: ...


class InProcessTransport:
    def __init__(self, server: SREServer | None = None):
        self.server = server or SREServer()

    def send(self, message: dict) -> dict | None:
        out = self.server.handle_line(json.dumps(message))
        return json.loads(out) if out else None


class StdioTransport:
    def __init__(self, command: list[str] | None = None):
        cmd = command or [sys.executable, "-m", "labs.mcp_sre.server"]
        self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", bufsize=1,
        )

    def send(self, message: dict) -> dict | None:
        assert self.proc.stdin and self.proc.stdout
        self.proc.stdin.write(json.dumps(message) + "\n")
        self.proc.stdin.flush()
        if "id" not in message:          # notification：不會有回應
            return None
        return json.loads(self.proc.stdout.readline())

    def close(self) -> None:
        if self.proc.stdin:
            self.proc.stdin.close()
        self.proc.wait(timeout=5)


class MCPError(RuntimeError):
    def __init__(self, code: int, message: str):
        super().__init__(f"[{code}] {message}")
        self.code = code


class MCPClient:
    def __init__(self, transport: Transport):
        self.transport = transport
        self._next_id = 0
        self.server_info: dict = {}
        self.tools: dict[str, dict] = {}

    def _request(self, method: str, params: dict | None = None) -> Any:
        self._next_id += 1
        resp = self.transport.send(JSONRPCRequest(id=self._next_id, method=method, params=params or {}).model_dump())
        if resp is None:
            raise MCPError(-32603, "no response")
        if resp.get("error"):
            raise MCPError(resp["error"]["code"], resp["error"]["message"])
        return resp["result"]

    def connect(self) -> "MCPClient":
        self.server_info = self._request("initialize", {
            "protocolVersion": SUPPORTED_PROTOCOL_VERSIONS[0],
            "capabilities": {},
            "clientInfo": {"name": "sre-lab-client", "version": "2.0.0"},
        })
        self.transport.send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tools = {t["name"]: t for t in self._request("tools/list")["tools"]}
        return self

    def call(self, tool: str, /, **arguments: Any) -> CallToolResult:
        # tool 是 positional-only，所以工具參數也可以叫 name / tool is positional-only
        return CallToolResult.model_validate(self._request("tools/call", {"name": tool, "arguments": arguments}))

    def is_read_only(self, name: str) -> bool:
        return bool(self.tools[name].get("annotations", {}).get("readOnlyHint", False))


# ------------------------------------------------------------------ workflow

@dataclass
class ProposedChange:
    tool: str
    arguments: dict
    reason: str
    evidence: list[str]           # 引用的 runbook 段落 id，方便人工核對


@dataclass
class Diagnosis:
    service: str
    before: dict
    runbook_hits: list[dict] = field(default_factory=list)
    proposal: ProposedChange | None = None
    approved: bool | None = None
    after: dict | None = None
    log: list[str] = field(default_factory=list)


Approver = Callable[[ProposedChange], bool]


def deny_all(_: ProposedChange) -> bool:
    return False


def diagnose(client: MCPClient, service: str, approve: Approver = deny_all) -> Diagnosis:
    """
    1. 讀取服務狀態 → 2. 依症狀查 runbook → 3. 提出修改 → 4. 人工核准 → 5. 執行 → 6. 再讀一次驗證。
    預設 approve=deny_all：沒有明確核准就不會動到正式環境。
    """
    status = client.call("get_service_status", resource_type="cloud_run", name=service)
    if status.isError:
        raise LookupError(status.content[0].text)
    before = json.loads(status.content[0].text)
    d = Diagnosis(service=service, before=before)
    d.log.append(f"status={before['status']} p99={before['p99_latency_ms']}ms min_instances={before['min_instances']}")

    if before["status"] == "HEALTHY":
        d.log.append("healthy; nothing to do")
        return d

    symptom = "cloud run p99 latency 504 cold start min-instances"
    hits = json.loads(client.call("search_runbooks", query=symptom, top_k=3).content[0].text)
    d.runbook_hits = hits
    d.log.append("runbook sections: " + ", ".join(h["chunk_id"] for h in hits))

    # 這一步在真實系統中通常由 LLM 根據 runbook 內容提出；這裡用規則代替，讓 lab 可離線重現。
    # In production an LLM would draft this from the runbook text; a rule keeps the lab reproducible.
    if before["min_instances"] == 0 and any("min-instances" in h["text"] for h in hits):
        d.proposal = ProposedChange(
            tool="update_cloud_run_scaling",
            arguments={"name": service, "min_instances": 3, "max_instances": 30, "concurrency": 20, "cpu_boost": True},
            reason="min_instances=0 causes cold starts after traffic lulls; runbook recommends warm instances",
            evidence=[h["chunk_id"] for h in hits if "min-instances" in h["text"]],
        )
    if d.proposal is None:
        d.log.append("no matching remediation; escalate to on-call")
        return d

    needs_approval = not client.is_read_only(d.proposal.tool)
    d.approved = approve(d.proposal) if needs_approval else True
    d.log.append(f"proposal {d.proposal.arguments} approved={d.approved}")
    if not d.approved:
        return d

    result = client.call(d.proposal.tool, **d.proposal.arguments)
    if result.isError:
        d.log.append("change failed: " + result.content[0].text)
        return d
    after = json.loads(client.call("get_service_status", resource_type="cloud_run", name=service).content[0].text)
    d.after = after
    d.log.append(f"verified: status={after['status']} p99={after['p99_latency_ms']}ms")
    return d
