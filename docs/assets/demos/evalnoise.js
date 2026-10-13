// 第 7 章示範：同一個系統、同樣的真實通過率，只因為測試題數有限，分數會怎麼跳動。
// Chapter 7 demo: how much a score moves by chance alone, given a finite number of cases.
(function () {
  "use strict";
  function en() { return window.FDE_LANG && window.FDE_LANG() === "en"; }

  function simulate(p, n, runs) {
    var out = [];
    for (var r = 0; r < runs; r++) {
      var pass = 0;
      for (var i = 0; i < n; i++) if (Math.random() < p) pass++;
      out.push(pass / n);
    }
    return out;
  }

  function draw(svg, scores, p, n, threshold) {
    var W = 640, H = 170, pad = 34;
    var lo = 0.5, hi = 1.0;
    function x(v) { return pad + (Math.min(Math.max(v, lo), hi) - lo) / (hi - lo) * (W - 2 * pad); }
    var half = 1.96 * Math.sqrt(p * (1 - p) / n);
    var html = "";
    html += '<rect x="' + x(p - half) + '" y="20" width="' + Math.max(2, x(p + half) - x(p - half)) + '" height="' + (H - 60) + '" fill="var(--accent-soft)"/>';
    for (var t = 5; t <= 10; t++) {
      var v = t / 10;
      html += '<line x1="' + x(v) + '" y1="' + (H - 38) + '" x2="' + x(v) + '" y2="' + (H - 33) + '" stroke="var(--fg-faint)"/>';
      html += '<text x="' + x(v) + '" y="' + (H - 18) + '" text-anchor="middle" class="muted">' + Math.round(v * 100) + "%</text>";
    }
    html += '<line x1="' + pad + '" y1="' + (H - 38) + '" x2="' + (W - pad) + '" y2="' + (H - 38) + '" stroke="var(--border-strong)"/>';
    // stack dots per bucket
    var buckets = {};
    scores.forEach(function (s) {
      var key = Math.round(s * n);
      buckets[key] = (buckets[key] || 0) + 1;
      var cy = (H - 46) - (buckets[key] - 1) * 9;
      var fail = s < threshold;
      html += '<circle cx="' + x(s) + '" cy="' + Math.max(cy, 14) + '" r="4" fill="' + (fail ? "var(--bad)" : "var(--accent)") + '" opacity="0.85"/>';
    });
    html += '<line x1="' + x(p) + '" y1="14" x2="' + x(p) + '" y2="' + (H - 38) + '" stroke="var(--fg)" stroke-dasharray="3 3"/>';
    html += '<line x1="' + x(threshold) + '" y1="14" x2="' + x(threshold) + '" y2="' + (H - 38) + '" stroke="var(--bad)" stroke-width="1.5"/>';
    html += '<text x="' + (x(threshold) + 4) + '" y="24" class="muted" style="fill:var(--bad)">gate</text>';
    svg.innerHTML = html;
    return half;
  }

  function init() {
    var root = document.getElementById("noiseDemo");
    if (!root) return;
    var pIn = root.querySelector("#np"), nIn = root.querySelector("#nn"), tIn = root.querySelector("#nt");
    var svg = root.querySelector("svg"), out = root.querySelector(".output");
    var last = null;
    function run(resample) {
      var p = Number(pIn.value) / 100, n = Number(nIn.value), thr = Number(tIn.value) / 100;
      root.querySelector("#npv").textContent = pIn.value + "%";
      root.querySelector("#nnv").textContent = n;
      root.querySelector("#ntv").textContent = tIn.value + "%";
      if (resample || !last || last.p !== p || last.n !== n) last = { p: p, n: n, scores: simulate(p, n, 30) };
      var half = draw(svg, last.scores, p, n, thr);
      var fails = last.scores.filter(function (s) { return s < thr; }).length;
      var min = Math.min.apply(null, last.scores), max = Math.max.apply(null, last.scores);
      out.innerHTML = en()
        ? "30 runs of the <strong>same</strong> system (true pass rate " + Math.round(p * 100) + "%) on " + n + " cases.\n" +
          "Observed range: " + (min * 100).toFixed(1) + "% – " + (max * 100).toFixed(1) + "%. One case = " + (100 / n).toFixed(1) + " points.\n" +
          "≈95% of runs fall within ±" + (half * 100).toFixed(1) + " points (shaded).\n" +
          '<span class="' + (fails ? "err" : "ok") + '">' + fails + " / 30 runs would fail a gate at " + Math.round(thr * 100) + "% even though nothing changed.</span>"
        : "<strong>同一個</strong>系統（真實通過率 " + Math.round(p * 100) + "%）在 " + n + " 題上跑 30 次。\n" +
          "觀察到的範圍：" + (min * 100).toFixed(1) + "% – " + (max * 100).toFixed(1) + "%。一題 = " + (100 / n).toFixed(1) + " 個百分點。\n" +
          "約 95% 的結果落在 ±" + (half * 100).toFixed(1) + " 個百分點內（陰影區）。\n" +
          '<span class="' + (fails ? "err" : "ok") + '">即使什麼都沒改，30 次中有 ' + fails + " 次會被 " + Math.round(thr * 100) + "% 的門檻擋下。</span>";
    }
    [pIn, nIn, tIn].forEach(function (el) { el.addEventListener("input", function () { run(false); }); });
    root.querySelector("#nrun").addEventListener("click", function () { run(true); });
    document.addEventListener("fde-lang", function () { run(false); });
    run(true);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
