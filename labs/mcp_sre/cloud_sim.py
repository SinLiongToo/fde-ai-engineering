"""
模擬的雲端環境 / Simulated cloud environment.

⚠ 這裡沒有呼叫任何真正的 GCP API。數值與「擴容後延遲恢復」的行為都是寫死的，
  目的是讓 lab 離線可跑。要接真實環境，請用 google-cloud-run 與
  Cloud Monitoring 的 client library 實作同樣的三個方法。
⚠ Nothing here calls real GCP APIs. Numbers and recovery behaviour are scripted.
"""

from __future__ import annotations

import copy
from typing import Any, Dict, Optional


class CloudSimulator:
    def __init__(self) -> None:
        self._run: Dict[str, Dict[str, Any]] = {
            "payment-gateway": {
                "service": "payment-gateway", "region": "asia-east1", "status": "DEGRADED",
                "min_instances": 0, "max_instances": 10, "concurrency": 80, "cpu_boost": False,
                "p99_latency_ms": 1420, "error_rate_5xx": 0.038,
                "recent_events": ["cold starts observed after 02:00 traffic lull"],
            },
            "order-processor": {
                "service": "order-processor", "region": "asia-east1", "status": "HEALTHY",
                "min_instances": 2, "max_instances": 20, "concurrency": 20, "cpu_boost": True,
                "p99_latency_ms": 115, "error_rate_5xx": 0.0, "recent_events": [],
            },
        }
        self._sql: Dict[str, Dict[str, Any]] = {
            "ledger-db": {
                "instance": "ledger-db", "version": "POSTGRES_16", "cpu_utilization": 0.92,
                "connections": 182, "max_connections": 200,
                "missing_indexes": ["knowledge_chunks(embedding) hnsw"],
            }
        }
        self.change_log: list[dict] = []

    def get_cloud_run(self, name: str) -> Optional[Dict[str, Any]]:
        svc = self._run.get(name)
        return copy.deepcopy(svc) if svc else None

    def get_cloud_sql(self, name: str) -> Optional[Dict[str, Any]]:
        inst = self._sql.get(name)
        return copy.deepcopy(inst) if inst else None

    def update_scaling(self, name: str, min_instances: int, max_instances: int,
                       concurrency: Optional[int] = None, cpu_boost: Optional[bool] = None) -> Dict[str, Any]:
        if name not in self._run:
            raise KeyError(f"Cloud Run service '{name}' not found")
        if not 0 <= min_instances <= max_instances <= 100:
            raise ValueError("require 0 <= min_instances <= max_instances <= 100")
        svc = self._run[name]
        before = copy.deepcopy(svc)
        svc.update(min_instances=min_instances, max_instances=max_instances)
        if concurrency is not None:
            svc["concurrency"] = concurrency
        if cpu_boost is not None:
            svc["cpu_boost"] = cpu_boost
        # 模擬：保留暖機實例後冷啟動消失 / scripted recovery once warm instances exist
        if min_instances >= 2 and svc["status"] == "DEGRADED":
            svc.update(status="HEALTHY", p99_latency_ms=190, error_rate_5xx=0.0005)
        self.change_log.append({"service": name, "before": before, "after": copy.deepcopy(svc)})
        return copy.deepcopy(svc)
