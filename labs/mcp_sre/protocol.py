"""
MCP（Model Context Protocol）訊息格式的最小子集 / A minimal subset of MCP message types.

MCP 建立在 JSON-RPC 2.0 之上：
- request：有 id，必須回應。
- notification：沒有 id，「不可以」回應（例如 notifications/initialized）。
- response：帶著對應的 id，裡面是 result 或 error 其中之一。

MCP sits on JSON-RPC 2.0. Requests carry an id and get a response;
notifications have no id and must NOT be answered.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

# 本 lab 實作的版本；server 會優先使用 client 要求的版本（若支援）。
SUPPORTED_PROTOCOL_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]

# JSON-RPC 標準錯誤碼 / standard JSON-RPC error codes
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603


class ToolAnnotations(BaseModel):
    """
    給 client 的「提示」，說明工具會不會改變外部狀態。
    注意：這是 server 自己宣稱的，只有在信任該 server 時才能作為決策依據。
    Hints from the server. Only trust them from servers you trust.
    """

    readOnlyHint: bool = False
    destructiveHint: bool = True
    idempotentHint: bool = False
    openWorldHint: bool = True


class ToolDefinition(BaseModel):
    name: str
    description: str
    inputSchema: Dict[str, Any]
    annotations: ToolAnnotations = Field(default_factory=ToolAnnotations)


class TextContent(BaseModel):
    type: str = "text"
    text: str


class CallToolResult(BaseModel):
    content: List[TextContent] = Field(default_factory=list)
    # isError=True：工具執行了但失敗（例如服務不存在）。這會回給模型讓它調整做法。
    # 協定層的錯誤（未知方法、參數錯誤）則用 JSON-RPC error。
    isError: bool = False


class JSONRPCRequest(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    method: str
    params: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_notification(self) -> bool:
        return self.id is None


class JSONRPCError(BaseModel):
    code: int
    message: str


class JSONRPCResponse(BaseModel):
    jsonrpc: str = "2.0"
    id: Optional[Union[str, int]] = None
    result: Optional[Any] = None
    error: Optional[JSONRPCError] = None

    def to_wire(self) -> str:
        data = {"jsonrpc": "2.0", "id": self.id}
        if self.error is not None:
            data["error"] = self.error.model_dump()
        else:
            data["result"] = self.result
        return json.dumps(data, ensure_ascii=False)
