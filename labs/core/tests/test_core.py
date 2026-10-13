import json

import pytest
from pydantic import ValidationError

from labs.core import evals
from labs.core.agent import Decision, new_agent, make_database
from labs.core.contracts import (
    EXAMPLE_LAZY, EXAMPLE_VALID, ClauseRiskAssessment, RepairExhausted, ScriptedLLM, generate_validated,
)
from labs.core.retrieval import (
    BM25, CORPUS, HybridRetriever, recall_at_k, reciprocal_rank, reciprocal_rank_fusion, tokenize,
)


# ------------------------------------------------------------- contracts (ch.4)

class TestContracts:
    def test_valid_payload(self):
        assert ClauseRiskAssessment(**EXAMPLE_VALID).clause_id == "CLAUSE-004"

    @pytest.mark.parametrize("text", ["TBD", "todo: fix", "N/A for now, sorry about that", "please contact admin asap ok"])
    def test_placeholders_rejected(self, text):
        with pytest.raises(ValidationError):
            ClauseRiskAssessment(**{**EXAMPLE_VALID, "mitigation": text + " " * 30})

    def test_word_boundary_avoids_false_positive(self):
        # "todos" 與 "mastodon" 不應該被當成 "todo"
        ok = "Update the todos table and the mastodon webhook config with SET lock_timeout."
        assert ClauseRiskAssessment(**{**EXAMPLE_VALID, "mitigation": ok})

    @pytest.mark.parametrize("field,value", [("clause_id", "BAD-1"), ("confidence", 1.5), ("findings", [])])
    def test_field_constraints(self, field, value):
        with pytest.raises(ValidationError):
            ClauseRiskAssessment(**{**EXAMPLE_VALID, field: value})

    def test_repair_loop_feeds_errors_back(self):
        llm = ScriptedLLM([json.dumps(EXAMPLE_LAZY), json.dumps(EXAMPLE_VALID)])
        obj, attempts = generate_validated(llm, "assess")
        assert obj.risk_level == "HIGH"
        assert [a["ok"] for a in attempts] == [False, True]
        second_call = llm.received[1]
        assert "mitigation" in second_call[-1]["content"]  # 模型看得到具體錯誤

    def test_citations_checked_against_retrieved_docs(self):
        raw = json.dumps({**EXAMPLE_VALID, "cited_clause_ids": ["CLAUSE-004", "CLAUSE-099"]})
        assert ClauseRiskAssessment.model_validate_json(raw)  # 沒有 context：不檢查
        with pytest.raises(ValidationError, match="CLAUSE-099"):
            ClauseRiskAssessment.model_validate_json(raw, context={"retrieved_ids": {"CLAUSE-003", "CLAUSE-004"}})

    def test_repair_loop_gives_up(self):
        llm = ScriptedLLM(["not json"] * 3)
        with pytest.raises(RepairExhausted) as exc:
            generate_validated(llm, "assess", max_attempts=3)
        assert len(exc.value.attempts) == 3


# ------------------------------------------------------------- retrieval (ch.5)

class TestRetrieval:
    def test_tokenizer_keeps_identifiers(self):
        assert "pay-4102" in tokenize("Error PAY-4102 occurred")
        assert "lock_timeout" in tokenize("set lock_timeout = 2s")

    def test_bm25_exact_id(self):
        top = BM25(CORPUS).search("PAY-4102", top_n=1)
        assert top[0][0].id == "CLAUSE-006"

    def test_bm25_misses_morphology_vector_does_not(self):
        r = HybridRetriever()
        res = r.search("how do I migrate a big postgres table safely")
        assert "CLAUSE-004" not in [d.id for d, _ in res.lexical]
        assert res.vector[0][0].id == "CLAUSE-004"
        assert res.fused[0][0].id == "CLAUSE-004"

    def test_rrf_math(self):
        fused = dict(reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60, top_n=3))
        assert fused["b"] == pytest.approx(1 / 62 + 1 / 61)
        assert fused["a"] == pytest.approx(1 / 61)
        assert max(fused, key=fused.get) == "b"

    def test_acl_filter(self):
        r = HybridRetriever()
        no_access = [d.id for d, _ in r.search("GDPR Article 44 personal data").fused]
        with_access = [d.id for d, _ in r.search("GDPR Article 44 personal data", user_groups={"legal"}).fused]
        assert "CLAUSE-002" not in no_access
        assert with_access[0] == "CLAUSE-002"

    def test_metrics(self):
        assert recall_at_k(["a", "b", "c"], {"c", "d"}, k=3) == 0.5
        assert reciprocal_rank(["x", "y", "a"], {"a"}) == pytest.approx(1 / 3)


# ------------------------------------------------------------- agent (ch.6)

class TestAgent:
    def test_read_only_goal_completes_without_approval(self):
        agent, _ = new_agent()
        s = agent.start("Report tokens that expired over a month ago")
        assert s.status == "done"
        assert [h["tool"] for h in s.history] == ["run_select"]

    def test_destructive_tool_interrupts_and_resumes(self):
        agent, db = new_agent()
        s = agent.start("Clean up expired tokens")
        assert s.status == "waiting_approval"
        assert s.pending["tool"] == "delete_expired_tokens"
        assert db.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0] == 5  # 尚未執行

        s = agent.resume(s.thread_id, Decision(True, "alice@example.com", "OPS-123"))
        assert s.status == "done"
        assert s.approvals[0]["approver"] == "alice@example.com"
        assert db.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0] == 2

    def test_rejection_stops_without_side_effects(self):
        agent, db = new_agent()
        s = agent.start("Clean up expired tokens")
        s = agent.resume(s.thread_id, Decision(False, "bob@example.com", "wrong environment"))
        assert s.status == "rejected"
        assert db.execute("SELECT COUNT(*) FROM api_tokens").fetchone()[0] == 5

    def test_cannot_resume_thread_that_is_not_waiting(self):
        agent, _ = new_agent()
        s = agent.start("Report tokens")
        with pytest.raises(ValueError):
            agent.resume(s.thread_id, Decision(True, "alice@example.com"))

    def test_resume_from_checkpoint_after_restart(self):
        agent, _ = new_agent()
        s = agent.start("Clean up expired tokens")
        restored = agent.store.latest(s.thread_id)       # 從 JSON 還原，模擬程序重啟
        assert restored.status == "waiting_approval"
        assert restored.pending == s.pending
        assert len(agent.store.history(s.thread_id)) >= 2

    def test_step_budget(self):
        agent, _ = new_agent()
        s = agent.start("Clean up expired tokens", max_steps=1)
        assert s.status == "halted"

    def test_read_connection_is_enforced_by_database(self):
        _, ro = make_database()
        with pytest.raises(Exception, match="readonly"):
            ro.execute("DELETE FROM api_tokens")


# ------------------------------------------------------------- evals (ch.7)

class TestEvalGate:
    def test_current_system_meets_baseline(self):
        _, summary = evals.run()
        baseline = json.loads(evals.BASELINE_PATH.read_text(encoding="utf-8"))
        assert evals.compare(summary, baseline) == []

    def test_gate_catches_regression(self):
        def broken(query, groups):           # 永遠回傳同一份文件
            return [("CLAUSE-005", "irrelevant")]
        _, summary = evals.run(broken)
        baseline = json.loads(evals.BASELINE_PATH.read_text(encoding="utf-8"))
        assert any("recall" in p for p in evals.compare(summary, baseline))

    def test_gate_catches_acl_leak(self):
        retriever = HybridRetriever()

        def leaky(query, groups):            # 忘記傳入使用者群組 → 用最高權限查
            res = retriever.search(query, user_groups={"legal", "security"})
            return [(d.id, d.text) for d, _ in res.fused]
        _, summary = evals.run(leaky)
        assert summary["acl_leaks"] > 0
        assert any("acl_leaks" in p for p in evals.compare(summary, summary))
