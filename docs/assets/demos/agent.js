// 第 6 章示範：與 labs/core/agent.py 相同的流程（planner → 工具 → 核准 → 恢復），逐步執行。
// Chapter 6 demo: the same flow as labs/core/agent.py, one step at a time.
(function () {
  "use strict";
  var TOKENS0 = [
    { id: 1, customer: "acme", expires_days_ago: 45 },
    { id: 2, customer: "acme", expires_days_ago: -10 },
    { id: 3, customer: "globex", expires_days_ago: 90 },
    { id: 4, customer: "initech", expires_days_ago: 5 },
    { id: 5, customer: "globex", expires_days_ago: 31 }
  ];
  var TOOLS = {
    run_select: { risk: "read" },
    delete_expired_tokens: { risk: "destructive" }
  };

  function en() { return window.FDE_LANG && window.FDE_LANG() === "en"; }
  function L(zh, e) { return en() ? e : zh; }

  var db, state, checkpoints, logLines;

  function reset(goal, maxSteps) {
    db = JSON.parse(JSON.stringify(TOKENS0));
    state = { thread_id: Math.random().toString(16).slice(2, 10), goal: goal, status: "running", steps: 0,
              max_steps: maxSteps, history: [], pending: null, approvals: [] };
    checkpoints = [];
    logLines = [];
    save("start");
  }
  function save(label) { checkpoints.push({ label: label, json: JSON.stringify(state) }); }
  function log(cls, msg) { logLines.push('<span class="' + cls + '">' + msg + "</span>"); }

  function plannerNext() {
    var done = state.history.map(function (h) { return h.tool; });
    if (done.indexOf("run_select") < 0)
      return { tool: "run_select", args: { sql: "SELECT customer, expires_days_ago FROM api_tokens WHERE expires_days_ago > 30" } };
    if (/clean/i.test(state.goal) && done.indexOf("delete_expired_tokens") < 0)
      return { tool: "delete_expired_tokens", args: { older_than_days: 30 } };
    return null;
  }
  function execute(call) {
    var entry = { tool: call.tool, args: call.args };
    if (call.tool === "run_select") {
      entry.result = db.filter(function (r) { return r.expires_days_ago > 30; }).map(function (r) { return [r.customer, r.expires_days_ago]; });
    } else if (call.tool === "delete_expired_tokens") {
      var before = db.length;
      db = db.filter(function (r) { return !(r.expires_days_ago > call.args.older_than_days); });
      entry.result = { deleted: before - db.length };
    }
    state.history.push(entry);
    state.steps += 1;
    log("ok", "✓ " + call.tool + " → " + JSON.stringify(entry.result));
  }

  // 執行一個「節點」：與 Python 的 _loop 相同，但每次只走一步
  function step() {
    if (state.status !== "running") return;
    if (state.steps >= state.max_steps) {
      state.status = "halted";
      log("err", L("■ 已達步數上限 max_steps=", "■ step budget reached, max_steps=") + state.max_steps);
      save("halted");
      return;
    }
    var call = plannerNext();
    if (!call) {
      state.status = "done";
      log("ok", L("■ planner 回傳 None：完成", "■ planner returned None: done"));
      save("done");
      return;
    }
    log("dim", "planner → " + call.tool + " " + JSON.stringify(call.args) + "  [risk=" + TOOLS[call.tool].risk + "]");
    if (TOOLS[call.tool].risk !== "read") {
      state.pending = call;
      state.status = "waiting_approval";
      log("warn", L("⏸ interrupt：非唯讀工具，等待人工核准（狀態已存檔，程序可以結束）",
                    "⏸ interrupt: non-read tool, waiting for approval (state saved; the process may exit)"));
      save("interrupt");
      return;
    }
    execute(call);
    save("after " + call.tool);
  }

  function decide(approved, approver) {
    if (state.status !== "waiting_approval") return;
    var call = state.pending;
    state.approvals.push({ tool: call.tool, args: call.args, approved: approved, approver: approver, at: new Date().toISOString() });
    state.pending = null;
    log(approved ? "ok" : "err", (approved ? "✓ approved by " : "✗ rejected by ") + approver);
    if (!approved) { state.status = "rejected"; save("rejected"); return; }
    state.status = "running";
    execute(call);
    save("after " + call.tool);
    // 與 Python 的 resume() 相同：核准後繼續執行，直到下一次中斷或結束
    var guard = 0;
    while (state.status === "running" && guard++ < 20) step();
  }

  function crashAndRestore() {
    var last = checkpoints[checkpoints.length - 1];
    state = JSON.parse(last.json);
    log("dim", L("↻ 模擬程序重啟：從最後一個 checkpoint（" + last.label + "）還原。thread_id 相同，狀態 = ",
                 "↻ simulated restart: restored from the last checkpoint (" + last.label + "). Same thread_id, status = ") + state.status);
  }

  function render(root) {
    var esc = window.FDE_ESCAPE || function (s) { return s; };
    var nodes = ["plan", "tool", "approval", "end"];
    var active = { running: "plan", waiting_approval: "approval", done: "end", rejected: "end", halted: "end" }[state.status];
    root.querySelector(".sm").innerHTML = nodes.map(function (n, i) {
      var cls = "node";
      if (n === active) cls += state.status === "waiting_approval" ? " paused" : state.status === "running" ? " active" :
        state.status === "done" ? " done" : " stopped";
      if (n === "tool" && state.history.length && state.status === "running") cls += " active";
      var label = { plan: "planner", tool: "tool", approval: L("人工核准", "approval"), end: state.status === "running" || state.status === "waiting_approval" ? "end" : state.status }[n];
      return (i ? '<span class="arrow">→</span>' : "") + '<span class="' + cls + '">' + label + "</span>";
    }).join("");
    root.querySelector("#agStatus").textContent = state.status;
    root.querySelector("#agSteps").textContent = state.steps + " / " + state.max_steps;
    root.querySelector("#agCk").textContent = checkpoints.length;
    root.querySelector("#agRows").textContent = db.length;
    root.querySelector(".output").innerHTML = logLines.join("\n") || '<span class="dim">' + L("按「下一步」開始", "Press Step to begin") + "</span>";
    var box = root.querySelector(".approval");
    box.hidden = state.status !== "waiting_approval";
    if (!box.hidden) {
      root.querySelector("#agPending").textContent = state.pending.tool + " " + JSON.stringify(state.pending.args);
    }
    root.querySelector("#agStep").disabled = state.status !== "running";
    var audit = root.querySelector("#agAudit");
    audit.textContent = state.approvals.length ? JSON.stringify(state.approvals, null, 2) : "[]";
    void esc;
  }

  function init() {
    var root = document.getElementById("agentDemo");
    if (!root) return;
    var goalSel = root.querySelector("#agGoal");
    var budget = root.querySelector("#agBudget");
    function restart() { reset(goalSel.value, Number(budget.value)); render(root); }
    goalSel.addEventListener("change", restart);
    budget.addEventListener("change", restart);
    root.querySelector("#agReset").addEventListener("click", restart);
    root.querySelector("#agStep").addEventListener("click", function () { step(); render(root); });
    root.querySelector("#agRun").addEventListener("click", function () {
      var guard = 0;
      while (state.status === "running" && guard++ < 20) step();
      render(root);
    });
    root.querySelector("#agCrash").addEventListener("click", function () { crashAndRestore(); render(root); });
    root.querySelector("#agApprove").addEventListener("click", function () {
      decide(true, root.querySelector("#agWho").value || "alice@example.com"); render(root);
    });
    root.querySelector("#agReject").addEventListener("click", function () {
      decide(false, root.querySelector("#agWho").value || "alice@example.com"); render(root);
    });
    document.addEventListener("fde-lang", function () { render(root); });
    restart();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
