// 中級篇的互動示範。搜尋邏輯與 labs/intermediate/search.py 相同（資料來自 handbook_data.js）。
// Demos for the Intermediate chapters; search mirrors labs/intermediate/search.py.
(function (global) {
  "use strict";
  function en() { return global.FDE_LANG && global.FDE_LANG() === "en"; }
  function L(zh, e) { return en() ? e : zh; }
  function esc(s) { return (global.FDE_ESCAPE || function (x) { return x; })(String(s)); }
  function onReady(fn) { if (typeof document === "undefined") return; if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn); else fn(); }

  // ================================================================ search (I3)
  var HB = global.FDE_HANDBOOK || { chunks: [], synonyms: {}, punct: "", min_score: 3 };
  var PUNCT = {}; Array.from(HB.punct).forEach(function (c) { PUNCT[c] = 1; });
  function pieces(text) {
    var chars = Array.from(text).filter(function (c) { return !PUNCT[c]; }).map(function (c) { return c.toLowerCase(); });
    var out = {};
    for (var i = 0; i + 1 < chars.length; i++) out[chars[i] + chars[i + 1]] = true;
    return out;
  }
  function expand(q) {
    var extra = Object.keys(HB.synonyms).filter(function (k) { return q.toLowerCase().indexOf(k.toLowerCase()) >= 0; })
      .map(function (k) { return HB.synonyms[k]; });
    return extra.length ? q + " " + extra.join(" ") : q;
  }
  var chunkPieces = {}, weight = {};
  (function () {
    var df = {};
    HB.chunks.forEach(function (c) {
      chunkPieces[c.id] = pieces(c.title + "：" + c.text);
      Object.keys(chunkPieces[c.id]).forEach(function (p) { df[p] = (df[p] || 0) + 1; });
    });
    var n = HB.chunks.length;
    Object.keys(df).forEach(function (p) { weight[p] = Math.log((n + 1) / (df[p] + 0.5)); });
  })();
  function round3(x) { return Math.round(x * 1000) / 1000; }
  function search(question, version, topN) {
    var q = pieces(version === "v3" ? expand(question) : question);
    var hits = [];
    HB.chunks.forEach(function (c) {
      var shared = Object.keys(q).filter(function (p) { return chunkPieces[c.id][p]; }).sort();
      if (!shared.length) return;
      var score = version === "v1" ? shared.length : shared.reduce(function (s, p) { return s + weight[p]; }, 0);
      hits.push({ id: c.id, title: c.title, score: round3(score), shared: shared });
    });
    hits.sort(function (a, b) { return b.score - a.score || (a.id < b.id ? -1 : 1); });
    if (version !== "v1") hits = hits.filter(function (h) { return h.score >= HB.min_score; });
    return hits.slice(0, topN || 3);
  }
  global.FDE_INTERMEDIATE = { search: search, expand: expand };

  onReady(function () {
    var root = document.getElementById("searchCmpDemo");
    if (!root) return;
    var input = root.querySelector("#scQ");
    function col(version) {
      var hits = search(input.value, version, 3);
      if (!hits.length) return '<p class="empty">' + L("找不到（回答「手冊沒寫」）", "Nothing found (answer: not in handbook)") + "</p>";
      return "<ol>" + hits.map(function (h) {
        return "<li><strong>" + h.id + "</strong> " + esc(h.title) + ' <span class="score">' + h.score + "</span><br>" +
          '<span class="score">' + h.shared.map(esc).join(" · ") + "</span></li>";
      }).join("") + "</ol>";
    }
    function run() {
      ["v1", "v2", "v3"].forEach(function (v) { root.querySelector("#sc" + v).innerHTML = col(v); });
      var ex = expand(input.value);
      root.querySelector("#scExpand").textContent = ex === input.value ? L("（沒有用到同義詞）", "(no synonyms used)") : ex;
    }
    root.querySelectorAll("[data-q]").forEach(function (b) { b.addEventListener("click", function () { input.value = b.getAttribute("data-q"); run(); }); });
    input.addEventListener("input", run);
    document.addEventListener("fde-lang", run);
    run();
  });

  // ================================================================ answer validator (I2)
  function validateAnswer(raw, retrieved, usedTool) {
    var errs = [], obj;
    try { obj = JSON.parse(raw); } catch (e) { return ["JSON 格式錯誤：" + e.message]; }
    if (typeof obj.found !== "boolean") errs.push("found 必須是 true 或 false");
    if (typeof obj.answer !== "string" || !obj.answer.length) errs.push("answer 不能是空的");
    if (!Array.isArray(obj.citations)) { errs.push("citations 必須是陣列"); return errs; }
    if (obj.found === true && !obj.citations.length && !usedTool) errs.push("found 為 true 時，citations 不能是空的：請附上段落編號");
    if (obj.found === false && obj.citations.length) errs.push("found 為 false 時，不應該有 citations");
    var unknown = obj.citations.filter(function (c) { return retrieved.indexOf(c) < 0; });
    if (unknown.length) errs.push("引用了這次沒有提供的段落：" + unknown.join(", ") + "；只能引用 [" + retrieved.join(", ") + "]");
    return errs;
  }
  global.FDE_INTERMEDIATE.validateAnswer = validateAnswer;
  var ANSWER_PRESETS = {
    good: '{"found": true, "answer": "請特休需在三個工作天前提出申請。", "citations": ["H01"]}',
    nocite: '{"found": true, "answer": "請特休需在三個工作天前提出申請。", "citations": []}',
    fake: '{"found": true, "answer": "請特休需在三個工作天前提出申請。", "citations": ["H07"]}',
    notfound: '{"found": false, "answer": "手冊沒有寫到這件事，建議詢問人資部門。", "citations": []}',
    contradict: '{"found": false, "answer": "手冊沒有寫到這件事。", "citations": ["H01"]}'
  };
  onReady(function () {
    var root = document.getElementById("answerDemo");
    if (!root) return;
    var ta = root.querySelector("textarea"), out = root.querySelector(".output");
    function run() {
      var errs = validateAnswer(ta.value, ["H01", "H03"], root.querySelector("#adTool").checked);
      out.innerHTML = errs.length
        ? '<span class="err">✗ ' + L("不合格，會把下面的訊息回給 AI 重試一次：", "Rejected; this goes back to the AI for one retry:") + "</span>\n" +
          esc("你上一次的回答沒有通過檢查：\n" + errs.map(function (e) { return "- " + e; }).join("\n") + "\n請修正後重新回答，只輸出 JSON。")
        : '<span class="ok">✓ ' + L("合格，可以顯示給員工。", "Accepted; safe to show the employee.") + "</span>";
    }
    root.querySelectorAll("[data-p]").forEach(function (b) {
      b.addEventListener("click", function () { ta.value = ANSWER_PRESETS[b.getAttribute("data-p")]; run(); });
    });
    ta.addEventListener("input", run);
    root.querySelector("#adTool").addEventListener("change", run);
    document.addEventListener("fde-lang", run);
    ta.value = ANSWER_PRESETS.good; run();
  });

  // ================================================================ tool trace (I4)
  onReady(function () {
    var root = document.getElementById("traceDemo");
    var trace = global.FDE_TOOL_TRACE;
    if (!root || !trace) return;
    var i = 0;
    var view = root.querySelector("#trView"), label = root.querySelector("#trLabel"), msgs = root.querySelector("#trMsgs");
    function describe(step) {
      if (step.kind === "request") return L("你的程式 → API：送出 " + step.messages.length + " 則訊息，提供工具 " + step.tools.join("、"),
        "Your code → API: sends " + step.messages.length + " messages, offering tools " + step.tools.join(", "));
      if (step.kind === "reply") return L("API → 你的程式：stop_reason = " + step.stop_reason, "API → your code: stop_reason = " + step.stop_reason) +
        (step.stop_reason === "tool_use" ? L("（AI 要求使用工具，你的程式要去執行）", " (the AI wants a tool; your code must run it)") : L("（回答完成）", " (answer complete)"));
      return L("檢查通過後，顯示給員工的最終回答", "Final answer shown to the employee after validation");
    }
    function render() {
      var step = trace[i];
      label.textContent = (i + 1) + " / " + trace.length + "　" + describe(step);
      var body = step.kind === "request" ? step.messages : step.kind === "reply" ? step.content : step.answer;
      view.textContent = JSON.stringify(body, null, 2);
      if (step.kind === "request") {
        msgs.innerHTML = step.messages.map(function (m) {
          var kind = typeof m.content === "string" ? (m.content.indexOf("<手冊>") >= 0 ? L("問題＋手冊段落", "question + handbook") : L("文字", "text"))
            : m.content.map(function (b) { return b.type; }).join(", ");
          return '<span class="chip" style="cursor:default">' + m.role + ": " + esc(kind) + "</span>";
        }).join(" ");
      } else msgs.innerHTML = "";
      root.querySelector("#trPrev").disabled = i === 0;
      root.querySelector("#trNext").disabled = i === trace.length - 1;
    }
    root.querySelector("#trPrev").addEventListener("click", function () { if (i > 0) { i--; render(); } });
    root.querySelector("#trNext").addEventListener("click", function () { if (i < trace.length - 1) { i++; render(); } });
    document.addEventListener("fde-lang", render);
    render();
  });

  // ================================================================ cost & history (I5)
  function costModel(opts) {
    // 每一輪送出的輸入 token = system + 手冊段落 + 本次問題 + 保留的歷史（每輪 = 問題 + 回答）
    var perTurnHistory = opts.question + opts.answer;
    var rows = [], totalIn = 0, totalOut = 0;
    for (var t = 1; t <= opts.turns; t++) {
      var kept = opts.keep === "all" ? t - 1 : Math.min(t - 1, opts.keep);
      var input = opts.system + opts.context + opts.question + kept * perTurnHistory;
      rows.push(input);
      totalIn += input; totalOut += opts.answer;
    }
    return { rows: rows, totalIn: totalIn, totalOut: totalOut };
  }
  global.FDE_INTERMEDIATE.costModel = costModel;
  onReady(function () {
    var root = document.getElementById("costDemo");
    if (!root) return;
    var price = (HB.prices && HB.prices[HB.model]) || [4, 20];
    function val(id) { return Number(root.querySelector("#" + id).value); }
    function run() {
      ["cmTurns", "cmContext"].forEach(function (id) { root.querySelector("#" + id + "V").textContent = root.querySelector("#" + id).value; });
      var base = { turns: val("cmTurns"), system: 300, context: val("cmContext"), question: 40, answer: 150 };
      var all = costModel(Object.assign({ keep: "all" }, base));
      var four = costModel(Object.assign({ keep: 4 }, base));
      var max = Math.max.apply(null, all.rows);
      var W = 640, H = 160, pad = 30, bw = (W - 2 * pad) / base.turns;
      var svg = "";
      all.rows.forEach(function (v, k) {
        var h = (v / max) * (H - 40), h2 = (four.rows[k] / max) * (H - 40);
        svg += '<rect x="' + (pad + k * bw + 1) + '" y="' + (H - 20 - h) + '" width="' + Math.max(1, bw / 2 - 2) + '" height="' + h + '" fill="var(--warn)" opacity="0.75"/>';
        svg += '<rect x="' + (pad + k * bw + bw / 2) + '" y="' + (H - 20 - h2) + '" width="' + Math.max(1, bw / 2 - 2) + '" height="' + h2 + '" fill="var(--accent)"/>';
      });
      svg += '<line x1="' + pad + '" y1="' + (H - 20) + '" x2="' + (W - pad) + '" y2="' + (H - 20) + '" stroke="var(--border-strong)"/>';
      svg += '<text x="' + pad + '" y="' + (H - 4) + '" class="muted">1</text><text x="' + (W - pad) + '" y="' + (H - 4) + '" text-anchor="end" class="muted">' + base.turns + "</text>";
      root.querySelector("svg").innerHTML = svg;
      function cost(r) { return (r.totalIn * price[0] + r.totalOut * price[1]) / 1e6; }
      root.querySelector(".output").innerHTML =
        '<span class="warn">■</span> ' + L("保留全部歷史", "Keep all history") + "：" + L("輸入共 ", "total input ") + all.totalIn.toLocaleString() + " tokens，US$" + cost(all).toFixed(4) +
        "\n" + '<span class="ok">■</span> ' + L("只保留最近 4 輪", "Keep last 4 turns") + "：" + L("輸入共 ", "total input ") + four.totalIn.toLocaleString() + " tokens，US$" + cost(four).toFixed(4) +
        "\n" + '<span class="dim">' + L("價格：", "Price: ") + HB.model + " $" + price[0] + " / $" + price[1] + L(" 每百萬 token（輸入/輸出），以官方定價頁為準。每輪假設 system 300、問題 40、回答 150 token。",
          " per million tokens (in/out); check the official pricing page. Assumes 300 system, 40 question, 150 answer tokens per turn.") + "</span>";
    }
    root.querySelectorAll("input").forEach(function (x) { x.addEventListener("input", run); });
    document.addEventListener("fde-lang", run);
    run();
  });
})(typeof window !== "undefined" ? window : globalThis);
