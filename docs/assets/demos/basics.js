// 入門篇的互動示範。資料與邏輯和 labs/beginner/*.py 相同。
// Demos for the Basics chapters; data and logic mirror labs/beginner/*.py.
(function (global) {
  "use strict";
  function en() { return global.FDE_LANG && global.FDE_LANG() === "en"; }
  function L(zh, e) { return en() ? e : zh; }
  function esc(s) { return (global.FDE_ESCAPE || function (x) { return x; })(String(s)); }
  function onReady(fn) { if (typeof document === "undefined") return; if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", fn); else fn(); }

  // ================================================================ B1: next character
  var TRAINING_TEXT = [
    "今天天氣很好，我們去公園散步。",
    "今天天氣很冷，我們在家喝咖啡。",
    "明天天氣很熱，我們去海邊游泳。",
    "我們在公園喝咖啡。",
    "我們去海邊散步。",
    "咖啡很好喝。"
  ];
  function train(sentences) {
    var counts = {};
    sentences.forEach(function (s) {
      var chars = Array.from(s);
      for (var i = 0; i + 1 < chars.length; i++) {
        var c = chars[i], n = chars[i + 1];
        counts[c] = counts[c] || {};
        counts[c][n] = (counts[c][n] || 0) + 1;
      }
    });
    return counts;
  }
  function nextProbs(counts, text) {
    var chars = Array.from(text);
    var f = counts[chars[chars.length - 1]];
    if (!f) return [];
    var total = 0; Object.keys(f).forEach(function (k) { total += f[k]; });
    return Object.keys(f).map(function (k) { return [k, f[k] / total]; })
      .sort(function (a, b) { return b[1] - a[1]; });
  }
  global.FDE_BASICS = { train: train, nextProbs: nextProbs, TRAINING_TEXT: TRAINING_TEXT };

  onReady(function () {
    var root = document.getElementById("nextCharDemo");
    if (!root) return;
    var model = train(TRAINING_TEXT);
    var text = "今天";
    var outText = root.querySelector("#ncText"), cands = root.querySelector("#ncCands"), note = root.querySelector("#ncNote");
    root.querySelector("#ncCorpus").innerHTML = TRAINING_TEXT.map(function (s) { return "<li>" + esc(s) + "</li>"; }).join("");
    function render() {
      outText.textContent = text;
      var probs = nextProbs(model, text);
      var done = text.slice(-1) === "。";
      if (done || !probs.length) {
        cands.innerHTML = '<span class="empty">' + (done ? L("句子結束了。按「重來」再試一次。", "The sentence ended. Press Reset to try again.")
          : L("模型沒看過這個字後面接什麼，猜不下去了。", "The model never saw what follows this character, so it can't continue.")) + "</span>";
      } else {
        cands.innerHTML = probs.map(function (p) {
          return '<button class="chip" type="button" data-c="' + esc(p[0]) + '">' + esc(p[0]) +
            ' <span style="color:var(--fg-faint)">' + Math.round(p[1] * 100) + "%</span></button>";
        }).join(" ");
      }
      var invented = text.slice(-1) === "。" && TRAINING_TEXT.indexOf(text) < 0 && TRAINING_TEXT.every(function (s) { return s.indexOf(text) < 0; });
      note.innerHTML = invented
        ? '<span class="warn">' + L("⚠ 這句話不在訓練資料裡！它很通順，但是是模型「編」出來的。",
            "⚠ This sentence isn't in the training data! It reads fine, but the model made it up.") + "</span>"
        : "";
    }
    cands.addEventListener("click", function (e) {
      var b = e.target.closest("[data-c]"); if (!b) return;
      text += b.getAttribute("data-c"); render();
    });
    root.querySelector("#ncAuto").addEventListener("click", function () {
      for (var i = 0; i < 30 && text.slice(-1) !== "。"; i++) {
        var probs = nextProbs(model, text); if (!probs.length) break;
        var r = Math.random(), acc = 0, pick = probs[0][0];
        for (var j = 0; j < probs.length; j++) { acc += probs[j][1]; if (r <= acc) { pick = probs[j][0]; break; } }
        text += pick;
      }
      render();
    });
    root.querySelector("#ncReset").addEventListener("click", function () {
      text = root.querySelector("#ncStart").value || "今天"; render();
    });
    root.querySelector("#ncStart").addEventListener("change", function () { text = this.value || "今天"; render(); });
    document.addEventListener("fde-lang", render);
    render();
  });

  // ================================================================ B2: conversation builder
  onReady(function () {
    var root = document.getElementById("convoDemo");
    if (!root) return;
    var history = [];
    var sys = root.querySelector("#cvSystem"), q = root.querySelector("#cvQ"), forget = root.querySelector("#cvForget");
    var out = root.querySelector("#cvJson"), info = root.querySelector("#cvInfo");
    var lastRequest = null, turn = 0;
    function render() {
      if (!lastRequest) {
        out.textContent = L("（輸入問題後按「送出」，這裡會顯示真正送給 API 的內容）", "(Type a question and press Send to see what is actually sent to the API)");
        info.innerHTML = "";
        return;
      }
      out.textContent = JSON.stringify(lastRequest, null, 2);
      var chars = lastRequest.system.length + lastRequest.messages.reduce(function (n, m) { return n + m.content.length; }, 0);
      info.innerHTML = L("第 " + turn + " 次請求：送出 <strong>" + lastRequest.messages.length + "</strong> 則訊息，共約 " + chars + " 個字。",
        "Request #" + turn + ": sending <strong>" + lastRequest.messages.length + "</strong> messages, about " + chars + " characters.") +
        (forget.checked && turn > 1 ? '<br><span class="err" style="color:var(--bad)">' +
          L("⚠ 沒有送出歷史：AI 不知道你們之前聊過什麼，「它」、「剛剛那個」都會看不懂。",
            "⚠ History not sent: the AI has no idea what came before, so \"it\" or \"that one\" means nothing to it.") + "</span>" : "");
    }
    root.querySelector("#cvSend").addEventListener("click", function () {
      var question = q.value.trim(); if (!question) return;
      turn += 1;
      var messages = (forget.checked ? [] : history.slice()).concat([{ role: "user", content: question }]);
      lastRequest = { model: "claude-opus-5-5", max_tokens: 1000, system: sys.value, messages: messages };
      history.push({ role: "user", content: question });
      history.push({ role: "assistant", content: L("（AI 的第 " + turn + " 個回答）", "(AI answer #" + turn + ")") });
      var nextQs = [L("可以舉個例子嗎？", "Can you give an example?"), L("那它跟常數有什麼不同？", "How is it different from a constant?"), L("謝謝！", "Thanks!")];
      q.value = nextQs[Math.min(turn - 1, nextQs.length - 1)];
      render();
    });
    root.querySelector("#cvReset").addEventListener("click", function () {
      history = []; lastRequest = null; turn = 0; q.value = L("什麼是變數？", "What is a variable?"); render();
    });
    forget.addEventListener("change", render);
    document.addEventListener("fde-lang", render);
    render();
  });

  // ================================================================ B3: prompt builder
  var PIECES = [
    { id: "context", zh: "背景：我是誰、寫給誰", en: "Context: who I am, who it's for",
      textZh: "我是軟體公司的工程師，要寫給直屬主管王經理。", textEn: "I'm an engineer at a software company writing to my manager, Ms. Wang.",
      gapZh: "你是誰？寫給誰？要多正式？", gapEn: "Who are you? Who is it for? How formal?" },
    { id: "details", zh: "具體內容：日期、原因", en: "Specifics: dates, reason",
      textZh: "我想在 11 月 20 日到 22 日請三天特休，原因是家人來訪。", textEn: "I want three days of annual leave, Nov 20–22, because family is visiting.",
      gapZh: "哪幾天？請什麼假？為什麼？", gapEn: "Which days? What kind of leave? Why?" },
    { id: "handover", zh: "要提到的事：工作交接", en: "Must mention: handover",
      textZh: "信中要說明：手上的報表會在 19 日前完成，緊急事項請聯絡同事陳小明。", textEn: "Mention that my report will be done by the 19th and urgent matters can go to my colleague Chen.",
      gapZh: "工作怎麼辦？誰代理？", gapEn: "What about my work? Who covers?" },
    { id: "format", zh: "格式與長度", en: "Format and length",
      textZh: "請用 email 格式，包含主旨，內文 150 字以內。", textEn: "Write it as an email with a subject line, under 120 words.",
      gapZh: "要多長？要不要主旨？", gapEn: "How long? Subject line or not?" },
    { id: "tone", zh: "語氣", en: "Tone",
      textZh: "語氣禮貌但不要過度客套。", textEn: "Polite, but not overly formal.",
      gapZh: "要多客氣？", gapEn: "How polite?" },
    { id: "unknown", zh: "不確定時怎麼辦", en: "What to do when unsure",
      textZh: "如果缺少必要資訊，請先問我，不要自己編。", textEn: "If anything essential is missing, ask me first instead of inventing it.",
      gapZh: "資訊不夠時，要自己編還是先問？", gapEn: "When information is missing, invent it or ask?" }
  ];
  onReady(function () {
    var root = document.getElementById("promptDemo");
    if (!root) return;
    var box = root.querySelector("#pbChecks"), out = root.querySelector("#pbPrompt"), gaps = root.querySelector("#pbGaps");
    box.innerHTML = PIECES.map(function (p) {
      return '<label style="display:flex;gap:.45rem;align-items:center;font-size:.9rem"><input type="checkbox" value="' + p.id + '">' +
        '<span><span lang="zh-Hant">' + p.zh + '</span><span lang="en">' + p.en + "</span></span></label>";
    }).join("");
    function render() {
      var on = {}; box.querySelectorAll("input:checked").forEach(function (c) { on[c.value] = true; });
      var lines = [L("幫我寫一封請假信。", "Write a leave request email for me.")];
      PIECES.forEach(function (p) { if (on[p.id]) lines.push(L(p.textZh, p.textEn)); });
      out.textContent = lines.join("\n");
      var missing = PIECES.filter(function (p) { return !on[p.id]; });
      gaps.innerHTML = missing.length
        ? "<strong>" + L("AI 還得自己猜：", "The AI still has to guess:") + "</strong><ul>" +
          missing.map(function (p) { return "<li>" + L(p.gapZh, p.gapEn) + "</li>"; }).join("") + "</ul>"
        : '<span style="color:var(--tip)">✓ ' + L("AI 需要的資訊都給了。剩下的就是它擅長的部分：把字寫好。",
            "Everything the AI needs is there. What's left is the part it's good at: writing it well.") + "</span>";
    }
    box.addEventListener("change", render);
    root.querySelector("#pbAll").addEventListener("click", function () { box.querySelectorAll("input").forEach(function (c) { c.checked = true; }); render(); });
    root.querySelector("#pbNone").addEventListener("click", function () { box.querySelectorAll("input").forEach(function (c) { c.checked = false; }); render(); });
    document.addEventListener("fde-lang", render);
    render();
  });

  // ================================================================ B4: handbook search
  var HANDBOOK = {
    H1: "特休假：到職滿六個月後有三天特休。請特休需在三個工作天前於系統提出申請，由直屬主管核准。",
    H2: "病假：一年內合計三十天以內，薪資折半發給。請病假超過三天需附醫生證明。",
    H3: "上班時間：週一至週五上午九點到下午六點，中午休息一小時。可彈性提早或延後三十分鐘上下班。",
    H4: "遠端工作：每週最多兩天可在家工作，需事先在團隊行事曆標註，並保持通訊軟體在線。",
    H5: "報帳：出差的交通與住宿費用，需在出差結束後十四天內附上收據報帳，逾期不受理。",
    H6: "設備：公司提供筆記型電腦與螢幕。設備遺失或損壞請立即通知 IT 部門，不要自行送修。"
  };
  var PUNCT = "，。？！、：；「」";
  function pieces(text) {
    var chars = Array.from(text).filter(function (ch) { return ch.trim() && PUNCT.indexOf(ch) < 0; });
    var out = {};
    for (var i = 0; i + 1 < chars.length; i++) out[chars[i] + chars[i + 1]] = true;
    return out;
  }
  function search(question, topN) {
    var q = pieces(question), scored = [];
    Object.keys(HANDBOOK).forEach(function (id) {
      var d = pieces(HANDBOOK[id]);
      var shared = Object.keys(q).filter(function (k) { return d[k]; }).sort();
      if (shared.length) scored.push({ id: id, score: shared.length, shared: shared });
    });
    // 與 Python 相同：先比分數，同分時編號大的排前面（sort(reverse=True) 的行為）
    scored.sort(function (a, b) { return b.score - a.score || (a.id < b.id ? 1 : a.id > b.id ? -1 : 0); });
    return scored.slice(0, topN || 2);
  }
  function buildPrompt(question, found) {
    var context = found.length ? found.map(function (f) { return "[" + f.id + "] " + HANDBOOK[f.id]; }).join("\n") : "（沒有找到相關段落）";
    return "請只根據下面的員工手冊內容回答問題，並在答案後面標註段落編號，例如 [H1]。\n" +
      "如果手冊裡沒有答案，請直接說「手冊沒有寫到這件事」，不要自己猜。\n\n" +
      "<手冊>\n" + context + "\n</手冊>\n\n問題：" + question;
  }
  global.FDE_BASICS.search = search;
  global.FDE_BASICS.buildPrompt = buildPrompt;
  global.FDE_BASICS.HANDBOOK = HANDBOOK;

  onReady(function () {
    var root = document.getElementById("handbookDemo");
    if (!root) return;
    var input = root.querySelector("#hbQ"), found = root.querySelector("#hbFound"), prompt = root.querySelector("#hbPrompt");
    root.querySelector("#hbDocs").innerHTML = Object.keys(HANDBOOK).map(function (id) {
      return "<li><strong>" + id + "</strong> " + esc(HANDBOOK[id]) + "</li>";
    }).join("");
    function highlight(text, shared) {
      var marks = new Array(text.length).fill(false);
      shared.forEach(function (s) { var i = -1; while ((i = text.indexOf(s, i + 1)) >= 0) { marks[i] = marks[i + 1] = true; } });
      // 連續的命中字元包在同一個 span 裡 / merge consecutive hits into one span
      var out = "", open = false;
      Array.from(text).forEach(function (ch, i) {
        if (marks[i] && !open) { out += '<span class="hit">'; open = true; }
        if (!marks[i] && open) { out += "</span>"; open = false; }
        out += esc(ch);
      });
      return out + (open ? "</span>" : "");
    }
    function run() {
      var res = search(input.value, 2);
      found.innerHTML = res.length ? "<ol>" + res.map(function (r) {
        return "<li><strong>" + r.id + "</strong> <span class=\"score\">" + L("相同片段 ", "shared pieces: ") + r.score + "</span><br>" + highlight(HANDBOOK[r.id], r.shared) + "</li>";
      }).join("") + "</ol>" : '<p class="empty">' + L("沒有找到相關段落", "No matching section") + "</p>";
      prompt.textContent = buildPrompt(input.value, res);
    }
    root.querySelectorAll("[data-q]").forEach(function (b) { b.addEventListener("click", function () { input.value = b.getAttribute("data-q"); run(); }); });
    input.addEventListener("input", run);
    document.addEventListener("fde-lang", run);
    run();
  });

  // ================================================================ B5: grade the answers yourself
  var GRADE = [
    { q: "請特休要提前幾天？", a: "請特休需在三個工作天前於系統提出申請。[H1]", must: ["三個工作天"], ok: true,
      whyZh: "正確，而且有標註出處。", whyEn: "Correct, with a citation." },
    { q: "病假超過幾天要附證明？", a: "病假超過三天不需要附任何證明。[H2]", must: ["三天"], ok: false,
      whyZh: "意思完全相反！但它包含關鍵字「三天」，所以只檢查關鍵字的自動評分會讓它通過。", whyEn: "It says the opposite! Yet it contains the keyword 三天, so a keyword-only check passes it." },
    { q: "一週可以在家工作幾天？", a: "每週最多兩天，需事先在團隊行事曆標註。", must: ["兩天"], ok: false,
      whyZh: "內容對，但沒有標註出處 [H4]。我們要求每個答案都要能查證。", whyEn: "Content is right but there's no citation [H4]. We require every answer to be checkable." },
    { q: "公司有提供午餐嗎？", a: "公司提供午餐補助每月 2,000 元。[H6]", must: [], ok: false,
      whyZh: "手冊根本沒寫這件事，這是編出來的。正確答案應該是「手冊沒有寫到這件事」。", whyEn: "The handbook says nothing about this; it's made up. The right answer is \"the handbook doesn't cover this\"." },
    { q: "出差收據要多久內報帳？", a: "出差結束後十四天內要附收據報帳，逾期不受理。[H5]", must: ["十四天"], ok: true,
      whyZh: "正確，有出處。", whyEn: "Correct, with a citation." }
  ];
  function autoCheck(item) {
    return item.must.every(function (w) { return item.a.indexOf(w) >= 0; });
  }
  global.FDE_BASICS.GRADE = GRADE;
  global.FDE_BASICS.autoCheck = autoCheck;

  onReady(function () {
    var root = document.getElementById("gradeDemo");
    if (!root) return;
    var list = root.querySelector("#gdList"), result = root.querySelector("#gdResult");
    var picks = {};
    function render(showAnswers) {
      list.innerHTML = GRADE.map(function (g, i) {
        var pick = picks[i];
        var row = '<div class="card" style="margin:.6rem 0"><div style="font-size:.9rem;color:var(--fg-muted)">' + L("問題", "Question") + "：" + esc(g.q) + "</div>" +
          '<div style="margin:.3rem 0 .5rem"><strong>AI：</strong>' + esc(g.a) + "</div>" +
          '<div class="row" style="margin:0">' +
          '<button class="chip" type="button" data-i="' + i + '" data-v="1" aria-pressed="' + (pick === true) + '">✓ ' + L("通過", "Pass") + "</button>" +
          '<button class="chip" type="button" data-i="' + i + '" data-v="0" aria-pressed="' + (pick === false) + '">✗ ' + L("不通過", "Fail") + "</button></div>";
        if (showAnswers) {
          var right = pick === g.ok;
          var auto = autoCheck(g);
          row += '<div style="margin-top:.5rem;font-size:.9rem">' +
            (pick === undefined ? "" : (right ? '<span style="color:var(--tip)">✓ ' + L("你判斷對了。", "You got it right.") + "</span> " : '<span style="color:var(--bad)">✗ ' + L("再看一次。", "Look again.") + "</span> ")) +
            L(g.whyZh, g.whyEn) + '<br><span style="color:var(--fg-faint)">' + L("只檢查關鍵字的自動評分：", "Keyword-only auto check: ") +
            (auto ? L("通過", "pass") : L("不通過", "fail")) + (auto !== g.ok ? L("（判斷錯了）", " (wrong)") : "") + "</span></div>";
        }
        return row + "</div>";
      }).join("");
      if (showAnswers) {
        var mine = GRADE.filter(function (g, i) { return picks[i] === g.ok; }).length;
        var autoRight = GRADE.filter(function (g) { return autoCheck(g) === g.ok; }).length;
        result.innerHTML = L("你答對 " + mine + " / 5。只檢查關鍵字的自動評分答對 " + autoRight + " / 5：它會漏掉「意思相反」、「沒寫出處」、「內容是編的」這類錯誤。",
          "You scored " + mine + " / 5. The keyword-only auto check scored " + autoRight + " / 5: it misses errors like \"says the opposite\", \"no citation\" and \"made up\".");
      } else {
        result.innerHTML = "";
      }
    }
    var revealed = false;
    list.addEventListener("click", function (e) {
      var b = e.target.closest("[data-i]"); if (!b) return;
      picks[b.getAttribute("data-i")] = b.getAttribute("data-v") === "1";
      render(revealed);
    });
    root.querySelector("#gdReveal").addEventListener("click", function () { revealed = true; render(true); });
    root.querySelector("#gdReset").addEventListener("click", function () { picks = {}; revealed = false; render(false); });
    document.addEventListener("fde-lang", function () { render(revealed); });
    render(false);
  });
})(typeof window !== "undefined" ? window : globalThis);
