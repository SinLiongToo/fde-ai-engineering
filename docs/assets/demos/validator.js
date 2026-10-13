// 第 4 章示範：與 labs/core/contracts.py 的 ClauseRiskAssessment 相同的驗證規則（JS 版）。
// Chapter 4 demo: the same rules as ClauseRiskAssessment in labs/core/contracts.py, in JS.
(function () {
  "use strict";
  var PLACEHOLDER = /\b(tbd|todo|fixme|n\/a|contact (the )?admin|check later|look at (the )?logs)\b/i;
  var RISK = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
  var BASE = {
    clause_id: "CLAUSE-004",
    title: "Zero-downtime schema migration",
    risk_level: "HIGH",
    confidence: 0.8,
    findings: ["Migration script does not set lock_timeout"],
    mitigation: "Add SET lock_timeout = '2s' before each ALTER TABLE and retry with backoff.",
    cited_clause_ids: ["CLAUSE-004"]
  };
  function variant(patch) { var o = JSON.parse(JSON.stringify(BASE)); Object.keys(patch).forEach(function (k) { if (patch[k] === undefined) delete o[k]; else o[k] = patch[k]; }); return JSON.stringify(o, null, 2); }
  var PRESETS = {
    valid: variant({}),
    lazy: variant({ mitigation: "TBD - contact admin for details on this issue." }),
    badid: variant({ clause_id: "clause 4", confidence: 1.4 }),
    missing: variant({ findings: [], risk_level: "SEVERE" }),
    hallucinated: variant({ cited_clause_ids: ["CLAUSE-004", "CLAUSE-099"] }),
    fenced: "```json\n" + variant({}) + "\n```"
  };
  var RETRIEVED = ["CLAUSE-003", "CLAUSE-004"];

  function validate(raw, checkCitations) {
    var errors = [];
    var obj;
    try { obj = JSON.parse(raw); } catch (e) {
      return [{ loc: "(root)", msg: "Invalid JSON: " + e.message }];
    }
    if (obj === null || typeof obj !== "object" || Array.isArray(obj)) return [{ loc: "(root)", msg: "Input should be an object" }];
    function req(k) { if (!(k in obj)) { errors.push({ loc: k, msg: "Field required" }); return false; } return true; }
    if (req("clause_id")) {
      if (typeof obj.clause_id !== "string") errors.push({ loc: "clause_id", msg: "Input should be a valid string" });
      else if (!/^CLAUSE-\d{3,4}$/.test(obj.clause_id)) errors.push({ loc: "clause_id", msg: "String should match pattern '^CLAUSE-\\d{3,4}$'" });
    }
    if (req("title")) {
      if (typeof obj.title !== "string") errors.push({ loc: "title", msg: "Input should be a valid string" });
      else if (obj.title.length < 3 || obj.title.length > 120) errors.push({ loc: "title", msg: "String should have 3 to 120 characters" });
    }
    if (req("risk_level") && RISK.indexOf(obj.risk_level) < 0)
      errors.push({ loc: "risk_level", msg: "Input should be 'CRITICAL', 'HIGH', 'MEDIUM' or 'LOW'" });
    if (req("confidence")) {
      if (typeof obj.confidence !== "number") errors.push({ loc: "confidence", msg: "Input should be a valid number" });
      else if (obj.confidence < 0 || obj.confidence > 1) errors.push({ loc: "confidence", msg: "Input should be between 0 and 1" });
    }
    if (req("findings")) {
      if (!Array.isArray(obj.findings)) errors.push({ loc: "findings", msg: "Input should be a valid list" });
      else if (obj.findings.length < 1) errors.push({ loc: "findings", msg: "List should have at least 1 item" });
      else if (obj.findings.some(function (f) { return typeof f !== "string" || !f.trim(); })) errors.push({ loc: "findings", msg: "Value error, findings must not contain blank items" });
    }
    if (req("mitigation")) {
      if (typeof obj.mitigation !== "string") errors.push({ loc: "mitigation", msg: "Input should be a valid string" });
      else if (obj.mitigation.length < 25) errors.push({ loc: "mitigation", msg: "String should have at least 25 characters" });
      else {
        var m = obj.mitigation.match(PLACEHOLDER);
        if (m) errors.push({ loc: "mitigation", msg: "Value error, mitigation contains placeholder text '" + m[0] + "'; give a concrete, actionable step" });
      }
    }
    var cited = Array.isArray(obj.cited_clause_ids) ? obj.cited_clause_ids : [];
    if (checkCitations) {
      var unknown = cited.filter(function (c) { return RETRIEVED.indexOf(c) < 0; });
      if (unknown.length) errors.push({ loc: "cited_clause_ids", msg: "Value error, cites clauses that were not retrieved: " + unknown.join(", ") });
    }
    return errors;
  }

  function render(box, raw, check) {
    var esc = window.FDE_ESCAPE || function (s) { return s; };
    var errors = validate(raw, check);
    if (!errors.length) {
      box.innerHTML = '<span class="ok">✓ valid</span>\n<span class="dim">' +
        (window.FDE_LANG && window.FDE_LANG() === "en" ? "Safe to pass downstream." : "可以交給下游程式使用。") + "</span>";
      return;
    }
    var lines = errors.map(function (e) { return '<span class="err">- ' + esc(e.loc) + ": " + esc(e.msg) + "</span>"; });
    var head = errors.length + " validation error" + (errors.length > 1 ? "s" : "");
    var feedback = "Your previous output failed validation:\n" + errors.map(function (e) { return "- " + e.loc + ": " + e.msg; }).join("\n") + "\nReturn corrected JSON only.";
    var label = window.FDE_LANG && window.FDE_LANG() === "en" ? "Message sent back to the model on retry:" : "重試時回傳給模型的訊息：";
    box.innerHTML = '<span class="err">✗ ' + head + "</span>\n" + lines.join("\n") +
      '\n\n<span class="dim">' + label + "</span>\n" + esc(feedback);
  }

  function init() {
    var root = document.getElementById("validatorDemo");
    if (!root) return;
    var ta = root.querySelector("textarea");
    var box = root.querySelector(".output");
    var cb = root.querySelector("#checkCitations");
    ta.value = PRESETS.valid;
    root.querySelectorAll("[data-preset]").forEach(function (b) {
      b.addEventListener("click", function () {
        root.querySelectorAll("[data-preset]").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
        b.setAttribute("aria-pressed", "true");
        ta.value = PRESETS[b.getAttribute("data-preset")];
        render(box, ta.value, cb.checked);
      });
    });
    root.querySelector("#runValidate").addEventListener("click", function () { render(box, ta.value, cb.checked); });
    cb.addEventListener("change", function () { render(box, ta.value, cb.checked); });
    document.addEventListener("fde-lang", function () { render(box, ta.value, cb.checked); });
    render(box, ta.value, cb.checked);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
