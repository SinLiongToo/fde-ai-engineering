"""
MCP server（stdio transport）/ MCP server over stdio.

啟動 / Run:
    python -m labs.mcp_sre.server

重點 / Notes
- stdout 只能輸出 JSON-RPC 訊息，一行一則。任何除錯訊息都要寫到 stderr，
  否則會破壞協定。
  stdout carries protocol messages only (one per line); log to stderr.
- 每個工具都附 annotations，讓 client 知道哪些操作會改變外部狀態。
  Every tool declares annotations so the client knows which ones change state.
- 參數在執行前先依 inputSchema 檢查。
  Arguments are checked against inputSchema before the tool runs.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable, Dict

from .cloud_sim import CloudSimulator
from .protocol import (
    INVALID_PARAMS, INVALID_REQUEST, METHOD_NOT_FOUND, PARSE_ERROR, SUPPORTED_PROTOCOL_VERSIONS,
    CallToolResult, JSONRPCError, JSONRPCRequest, JSONRPCResponse, TextContent, ToolAnnotations,
    ToolDefinition,
)
from .runbooks import RunbookSearch

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True)

_JSON_TYPES = {"string": str, "integer": int, "boolean": bool, "object": dict, "array": list}


def check_arguments(schema: Dict[str, Any], args: Dict[str, Any]) -> list[str]:
    """
    極簡的 JSON Schema 檢查（required、type、enum、未知欄位）。正式專案請用 jsonschema 套件。
    Minimal schema check. Use the `jsonschema` package in real projects.
    """
    errors = []
    props = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in args:
            errors.append(f"missing required argument '{name}'")
    for name, value in args.items():
        spec = props.get(name)
        if spec is None:
            errors.append(f"unknown argument '{name}'")
            continue
        expected = _JSON_TYPES.get(spec.get("type", ""))
        # bool 是 int 的子類別，要特別排除 / bool is a subclass of int in Python
        if expected and (not isinstance(value, expected) or (expected is int and isinstance(value, bool))):
            errors.append(f"argument '{name}' must be {spec['type']}")
        elif "enum" in spec and value not in spec["enum"]:
            errors.append(f"argument '{name}' must be one of {spec['enum']}")
    return errors


class SREServer:
    def __init__(self, cloud: CloudSimulator | None = None, runbooks: RunbookSearch | None = None):
        self.cloud = cloud or CloudSimulator()
        self.runbooks = runbooks or RunbookSearch()
        self.initialized = False
        self.tools: Dict[str, tuple[ToolDefinition, Callable[..., CallToolResult]]] = {}
        self._register()

    # ------------------------------------------------------------ tools

    def _register(self) -> None:
        self._add(ToolDefinition(
            name="search_runbooks",
            description="Search SRE runbooks. Returns the most relevant sections with their chunk ids.",
            inputSchema={"type": "object", "properties": {
                "query": {"type": "string", "description": "Symptom or question, e.g. 'cloud run 504 cold start'"},
                "top_k": {"type": "integer", "description": "Number of sections to return (1-5)"},
            }, "required": ["query"], "additionalProperties": False},
            annotations=READ_ONLY,
        ), self._search_runbooks)
        self._add(ToolDefinition(
            name="get_service_status",
            description="Read current health metrics of a Cloud Run service or Cloud SQL instance.",
            inputSchema={"type": "object", "properties": {
                "resource_type": {"type": "string", "enum": ["cloud_run", "cloud_sql"]},
                "name": {"type": "string", "description": "e.g. 'payment-gateway' or 'ledger-db'"},
            }, "required": ["resource_type", "name"], "additionalProperties": False},
            annotations=READ_ONLY,
        ), self._get_status)
        self._add(ToolDefinition(
            name="update_cloud_run_scaling",
            description="Change scaling settings of a Cloud Run service. Changes production; needs human approval.",
            inputSchema={"type": "object", "properties": {
                "name": {"type": "string"},
                "min_instances": {"type": "integer"},
                "max_instances": {"type": "integer"},
                "concurrency": {"type": "integer"},
                "cpu_boost": {"type": "boolean"},
            }, "required": ["name", "min_instances", "max_instances"], "additionalProperties": False},
            annotations=MUTATING,
        ), self._update_scaling)

    def _add(self, definition: ToolDefinition, fn: Callable[..., CallToolResult]) -> None:
        self.tools[definition.name] = (definition, fn)

    def _search_runbooks(self, query: str, top_k: int = 3) -> CallToolResult:
        hits = self.runbooks.search(query, top_k=max(1, min(top_k, 5)))
        return _text(json.dumps(hits, ensure_ascii=False, indent=2))

    def _get_status(self, resource_type: str, name: str) -> CallToolResult:
        data = self.cloud.get_cloud_run(name) if resource_type == "cloud_run" else self.cloud.get_cloud_sql(name)
        if data is None:
            # 工具層級的錯誤：用 isError 回給模型，讓它有機會換個名稱再試
            return _text(f"{resource_type} resource '{name}' not found", is_error=True)
        return _text(json.dumps(data, indent=2))

    def _update_scaling(self, name: str, min_instances: int, max_instances: int,
                        concurrency: int | None = None, cpu_boost: bool | None = None) -> CallToolResult:
        try:
            after = self.cloud.update_scaling(name, min_instances, max_instances, concurrency, cpu_boost)
        except (KeyError, ValueError) as e:
            return _text(str(e), is_error=True)
        return _text(json.dumps({"status": "applied", "service": after}, indent=2))

    # ------------------------------------------------------------ JSON-RPC

    def handle(self, req: JSONRPCRequest) -> JSONRPCResponse | None:
        if req.is_notification:
            if req.method == "notifications/initialized":
                self.initialized = True
            return None  # notification 不回應 / never answer a notification

        if req.method == "initialize":
            requested = req.params.get("protocolVersion")
            version = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0]
            return _ok(req, {
                "protocolVersion": version,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "sre-lab", "version": "2.0.0"},
            })
        if req.method == "ping":
            return _ok(req, {})
        if req.method == "tools/list":
            return _ok(req, {"tools": [d.model_dump() for d, _ in self.tools.values()]})
        if req.method == "tools/call":
            name = req.params.get("name")
            args = req.params.get("arguments") or {}
            if name not in self.tools:
                return _err(req, INVALID_PARAMS, f"unknown tool '{name}'")
            definition, fn = self.tools[name]
            problems = check_arguments(definition.inputSchema, args)
            if problems:
                return _err(req, INVALID_PARAMS, "; ".join(problems))
            return _ok(req, fn(**args).model_dump())
        return _err(req, METHOD_NOT_FOUND, f"method '{req.method}' not found")

    def handle_line(self, line: str) -> str | None:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as e:
            return JSONRPCResponse(error=JSONRPCError(code=PARSE_ERROR, message=f"parse error: {e}")).to_wire()
        try:
            req = JSONRPCRequest.model_validate(raw)
        except Exception as e:
            rid = raw.get("id") if isinstance(raw, dict) else None
            return JSONRPCResponse(id=rid, error=JSONRPCError(code=INVALID_REQUEST, message=str(e))).to_wire()
        resp = self.handle(req)
        return resp.to_wire() if resp else None

    def serve_stdio(self) -> None:
        stdin = open(sys.stdin.fileno(), "r", encoding="utf-8", closefd=False)
        stdout = open(sys.stdout.fileno(), "w", encoding="utf-8", closefd=False, newline="\n")
        print("sre-lab MCP server ready (stdio)", file=sys.stderr)
        for line in stdin:
            if not line.strip():
                continue
            out = self.handle_line(line)
            if out is not None:
                stdout.write(out + "\n")
                stdout.flush()


def _text(text: str, is_error: bool = False) -> CallToolResult:
    return CallToolResult(content=[TextContent(text=text)], isError=is_error)


def _ok(req: JSONRPCRequest, result: Any) -> JSONRPCResponse:
    return JSONRPCResponse(id=req.id, result=result)


def _err(req: JSONRPCRequest, code: int, message: str) -> JSONRPCResponse:
    return JSONRPCResponse(id=req.id, error=JSONRPCError(code=code, message=message))


if __name__ == "__main__":
    SREServer().serve_stdio()
