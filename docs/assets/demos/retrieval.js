// 第 5 章示範：與 labs/core/retrieval.py 相同的 BM25、字元 3-gram 向量與 RRF（JS 版）。
// Chapter 5 demo: the same BM25, char 3-gram vectors and RRF as labs/core/retrieval.py.
(function (global) {
  "use strict";

  var CORPUS = [
    ["CLAUSE-001", "Payment webhook latency SLA", "APAC payment gateway authorization webhooks must respond within 250 ms at P99 under peak load. Responses slower than 500 ms open a P1 incident.", ["everyone"]],
    ["CLAUSE-002", "Cross-border transfer of personal data", "Personal data of EU customers stays in the Frankfurt region. Transfers outside the EU require pseudonymization and a documented legal basis under GDPR Article 44.", ["legal", "security"]],
    ["CLAUSE-003", "Destructive database operations", "DROP, TRUNCATE and unbounded DELETE statements on production ledgers require approval from two engineers and a verified snapshot taken within the last hour.", ["everyone"]],
    ["CLAUSE-004", "Zero-downtime schema migration", "DDL on high-traffic PostgreSQL tables must set lock_timeout = 2s and statement_timeout = 5s so a blocked migration fails fast instead of queueing every query behind its lock.", ["everyone"]],
    ["CLAUSE-005", "Model API rate limits", "Calls to external model APIs use exponential backoff with jitter and a per-tenant limit of 100 requests per minute to protect the shared token budget.", ["everyone"]],
    ["CLAUSE-006", "Incident error code PAY-4102", "PAY-4102 means the card network rejected the authorization because the merchant category code is missing. Retrying will not help; fix the merchant profile.", ["everyone"]],
    ["CLAUSE-007", "Secrets handling", "API keys and database passwords are read from the secret manager at startup. Secrets never appear in source code, logs, prompts or model outputs.", ["security"]],
    ["CLAUSE-008", "Read replica usage", "Analytics and reporting queries run against the read replica. The primary database only serves transactional traffic from the checkout service.", ["everyone"]],
    ["CLAUSE-009", "Data retention", "Raw chat transcripts are deleted after 30 days. Aggregated, anonymized metrics may be kept for two years for capacity planning.", ["legal"]],
    ["CLAUSE-010", "On-call escalation", "If the primary on-call engineer does not acknowledge a P1 page within 10 minutes, the page escalates to the secondary and then to the engineering manager.", ["everyone"]]
  ].map(function (r) { return { id: r[0], title: r[1], text: r[2], groups: r[3], content: r[1] + "\n" + r[2] }; });

  var STOP = {};
  "a an the and or of to in on for is are be by do does i how what when with from at it this that".split(" ").forEach(function (w) { STOP[w] = 1; });
  var TOKEN_RE = /[a-z0-9]+(?:[-_][a-z0-9]+)*/g;
  function tokenize(text) { return (text.toLowerCase().match(TOKEN_RE) || []).filter(function (t) { return !STOP[t]; }); }
  function counter(arr) { var c = {}; arr.forEach(function (x) { c[x] = (c[x] || 0) + 1; }); return c; }

  // ---------------- BM25 (k1=1.2, b=0.75, Lucene idf)
  var K1 = 1.2, B = 0.75;
  var docTokens = CORPUS.map(function (d) { return tokenize(d.content); });
  var docTf = docTokens.map(counter);
  var avgdl = docTokens.reduce(function (s, t) { return s + t.length; }, 0) / CORPUS.length;
  var df = {};
  docTokens.forEach(function (toks) { Object.keys(counter(toks)).forEach(function (t) { df[t] = (df[t] || 0) + 1; }); });
  var idf = {};
  Object.keys(df).forEach(function (t) { idf[t] = Math.log(1 + (CORPUS.length - df[t] + 0.5) / (df[t] + 0.5)); });

  function bm25(query) {
    var q = tokenize(query);
    return CORPUS.map(function (d, i) {
      var tf = docTf[i], dl = docTokens[i].length, s = 0, matched = [];
      q.forEach(function (t) {
        if (!tf[t]) return;
        var f = tf[t];
        s += idf[t] * f * (K1 + 1) / (f + K1 * (1 - B + B * dl / avgdl));
        matched.push(t);
      });
      return { doc: d, score: s, matched: matched };
    }).filter(function (x) { return x.score > 0; }).sort(function (a, b) { return b.score - a.score; });
  }

  // ---------------- char 3-gram TF-IDF (stand-in for embeddings)
  function ngrams(text) {
    var s = " " + tokenize(text).join(" ") + " ", out = [];
    for (var i = 0; i + 3 <= s.length; i++) out.push(s.slice(i, i + 3));
    return out;
  }
  var gramDf = {}, docGrams = CORPUS.map(function (d) { return counter(ngrams(d.content)); });
  docGrams.forEach(function (g) { Object.keys(g).forEach(function (k) { gramDf[k] = (gramDf[k] || 0) + 1; }); });
  var gramIdf = {};
  Object.keys(gramDf).forEach(function (k) { gramIdf[k] = Math.log((1 + CORPUS.length) / (1 + gramDf[k])) + 1; });
  function embed(text) {
    var c = counter(ngrams(text)), v = {}, norm = 0;
    Object.keys(c).forEach(function (g) { v[g] = c[g] * (gramIdf[g] || 0); norm += v[g] * v[g]; });
    norm = Math.sqrt(norm) || 1;
    Object.keys(v).forEach(function (g) { v[g] /= norm; });
    return v;
  }
  var docVecs = CORPUS.map(function (d) { return embed(d.content); });
  function cosine(a, b) { var s = 0; Object.keys(a).forEach(function (k) { if (b[k]) s += a[k] * b[k]; }); return s; }
  function vector(query) {
    var q = embed(query);
    return CORPUS.map(function (d, i) { return { doc: d, score: cosine(q, docVecs[i]) }; })
      .sort(function (a, b) { return b.score - a.score; });
  }

  // ---------------- RRF
  function rrf(rankings, k) {
    var scores = {}, parts = {};
    rankings.forEach(function (ranking, r) {
      ranking.forEach(function (id, idx) {
        var c = 1 / (k + idx + 1);
        scores[id] = (scores[id] || 0) + c;
        (parts[id] = parts[id] || []).push({ list: r, rank: idx + 1, c: c });
      });
    });
    return Object.keys(scores).map(function (id) { return { id: id, score: scores[id], parts: parts[id] }; })
      .sort(function (a, b) { return b.score - a.score; });
  }

  function search(query, groups, opts) {
    opts = opts || {};
    var candidates = opts.candidates || 5, k = opts.k || 60, topN = opts.topN || 3;
    var g = {}; (groups || []).concat(["everyone"]).forEach(function (x) { g[x] = 1; });
    var allowed = function (d) { return opts.ignoreAcl || d.groups.some(function (x) { return g[x]; }); };
    var lex = bm25(query).filter(function (x) { return allowed(x.doc); }).slice(0, candidates);
    var vec = vector(query).filter(function (x) { return allowed(x.doc); }).slice(0, candidates);
    var fused = rrf([lex.map(function (x) { return x.doc.id; }), vec.map(function (x) { return x.doc.id; })], k).slice(0, topN);
    return { lexical: lex, vector: vec, fused: fused, tokens: tokenize(query) };
  }

  global.FDE_RETRIEVAL = { CORPUS: CORPUS, tokenize: tokenize, search: search, rrf: rrf };

  // ---------------- UI
  function init() {
    var root = document.getElementById("retrievalDemo");
    if (!root) return;
    var input = root.querySelector("#rq");
    var esc = global.FDE_ESCAPE || function (s) { return s; };
    var byId = {}; CORPUS.forEach(function (d) { byId[d.id] = d; });
    function en() { return global.FDE_LANG && global.FDE_LANG() === "en"; }
    function groups() {
      return Array.prototype.map.call(root.querySelectorAll("input[name=grp]:checked"), function (c) { return c.value; });
    }
    function list(rows, fmt) {
      if (!rows.length) return '<p class="empty">' + (en() ? "no results" : "沒有結果") + "</p>";
      return "<ol>" + rows.map(fmt).join("") + "</ol>";
    }
    function run() {
      var k = Number(root.querySelector("#rk").value);
      root.querySelector("#rkv").textContent = k;
      var res = search(input.value, groups(), { k: k, ignoreAcl: root.querySelector("#noacl").checked });
      var lexHtml = list(res.lexical, function (x) {
        return "<li><strong>" + x.doc.id + "</strong> <span class=\"score\">" + x.score.toFixed(3) + "</span><br><span class=\"score\">" +
          (en() ? "matched: " : "命中：") + x.matched.map(function (t) { return '<span class="hit">' + esc(t) + "</span>"; }).join(" ") + "</span></li>";
      });
      var vecHtml = list(res.vector, function (x) {
        return "<li><strong>" + x.doc.id + "</strong> <span class=\"score\">" + x.score.toFixed(3) + "</span></li>";
      });
      var fusedHtml = list(res.fused, function (x) {
        var expl = x.parts.map(function (p) { return "1/(" + k + "+" + p.rank + ")"; }).join(" + ");
        return "<li><strong>" + x.id + "</strong> <span class=\"score\">" + x.score.toFixed(4) + "</span><br><span class=\"score\">" + expl +
          "</span><br><span style=\"font-size:.82rem\">" + esc(byId[x.id].title) + "</span></li>";
      });
      root.querySelector("#colLex").innerHTML = lexHtml;
      root.querySelector("#colVec").innerHTML = vecHtml;
      root.querySelector("#colRrf").innerHTML = fusedHtml;
      root.querySelector("#rtokens").textContent = res.tokens.join(" · ") || "—";
    }
    root.querySelectorAll("[data-q]").forEach(function (b) {
      b.addEventListener("click", function () { input.value = b.getAttribute("data-q"); run(); });
    });
    input.addEventListener("input", run);
    root.querySelectorAll("input[type=checkbox], input[type=range]").forEach(function (c) { c.addEventListener("input", run); });
    document.addEventListener("fde-lang", run);
    run();
  }
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
  }
})(typeof window !== "undefined" ? window : globalThis);
