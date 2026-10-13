import json

import pytest

from labs.mcp_sre.client import InProcessTransport, MCPClient, MCPError, StdioTransport, diagnose
from labs.mcp_sre.protocol import INVALID_PARAMS, METHOD_NOT_FOUND
from labs.mcp_sre.runbooks import load_chunks
from labs.mcp_sre.server import SREServer


@pytest.fixture
def server():
    return SREServer()


@pytest.fixture
def client(server):
    return MCPClient(InProcessTransport(server)).connect()


def test_handshake_and_discovery(client, server):
    assert client.server_info["protocolVersion"] == "2025-06-18"
    assert server.initialized  # notifications/initialized 已收到
    assert set(client.tools) == {"search_runbooks", "get_service_status", "update_cloud_run_scaling"}
    assert client.is_read_only("search_runbooks")
    assert not client.is_read_only("update_cloud_run_scaling")


def test_version_negotiation(server):
    resp = json.loads(server.handle_line(json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05"}})))
    assert resp["result"]["protocolVersion"] == "2024-11-05"


def test_notifications_get_no_response(server):
    assert server.handle_line('{"jsonrpc": "2.0", "method": "notifications/initialized"}') is None


def test_protocol_errors(server):
    unknown = json.loads(server.handle_line('{"jsonrpc":"2.0","id":7,"method":"resources/list"}'))
    assert unknown["error"]["code"] == METHOD_NOT_FOUND and unknown["id"] == 7
    bad_json = json.loads(server.handle_line("{not json"))
    assert bad_json["error"]["code"] == -32700


@pytest.mark.parametrize("args,needle", [
    ({}, "missing required argument 'query'"),
    ({"query": "x", "top_k": "3"}, "must be integer"),
    ({"query": "x", "rm": "-rf"}, "unknown argument 'rm'"),
])
def test_argument_validation(client, args, needle):
    with pytest.raises(MCPError) as exc:
        client.call("search_runbooks", **args)
    assert exc.value.code == INVALID_PARAMS and needle in str(exc.value)


def test_tool_error_is_result_not_protocol_error(client):
    res = client.call("get_service_status", resource_type="cloud_run", name="does-not-exist")
    assert res.isError and "not found" in res.content[0].text


def test_runbook_chunks_and_search(client):
    chunks = load_chunks()
    assert all(c.id.startswith("GCP-RUNBOOK-") for c in chunks)
    hits = json.loads(client.call("search_runbooks", query="cloud run cold start min-instances").content[0].text)
    assert hits[0]["chunk_id"].startswith("GCP-RUNBOOK-001")


def test_workflow_without_approval_changes_nothing(client, server):
    d = diagnose(client, "payment-gateway")             # 預設 deny_all
    assert d.proposal is not None and d.approved is False
    assert server.cloud.change_log == []
    assert server.cloud.get_cloud_run("payment-gateway")["min_instances"] == 0


def test_workflow_with_approval_applies_and_verifies(client, server):
    seen = []
    d = diagnose(client, "payment-gateway", approve=lambda p: seen.append(p) or True)
    assert seen[0].evidence  # 提案附上 runbook 證據
    assert d.after["status"] == "HEALTHY"
    assert len(server.cloud.change_log) == 1


def test_healthy_service_needs_nothing(client):
    d = diagnose(client, "order-processor")
    assert d.proposal is None


def test_real_stdio_transport():
    t = StdioTransport()
    try:
        c = MCPClient(t).connect()
        res = c.call("get_service_status", resource_type="cloud_sql", name="ledger-db")
        assert json.loads(res.content[0].text)["version"] == "POSTGRES_16"
    finally:
        t.close()
