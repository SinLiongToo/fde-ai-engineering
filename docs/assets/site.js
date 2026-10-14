// 共用的頁面行為：側欄、目錄、語言/主題切換、程式碼複製、小測驗、學習進度。
// Shared page behaviour: sidebar, TOC, language/theme, copy buttons, quizzes, progress.
(function () {
  "use strict";

  // part: "basics" = 入門篇，"core" = 進階篇。順序就是閱讀順序（上一章／下一章）。
  var CHAPTERS = [
    { slug: "b1-what-is-llm", part: "basics", num: "B1", zh: "AI 語言模型在做什麼", en: "What a language model does", min: 15 },
    { slug: "b2-first-api-call", part: "basics", num: "B2", zh: "第一次呼叫 AI", en: "Your first API call", min: 15 },
    { slug: "b3-prompting", part: "basics", num: "B3", zh: "把話說清楚：寫 prompt", en: "Saying it clearly: prompts", min: 15 },
    { slug: "b4-your-documents", part: "basics", num: "B4", zh: "讓 AI 讀你的文件", en: "Answering from your documents", min: 15 },
    { slug: "b5-is-it-good", part: "basics", num: "B5", zh: "它做得好嗎？簡單的測試", en: "Is it any good? Simple tests", min: 15 },
    { slug: "i1-project-setup", part: "intermediate", num: "I1", zh: "專案起步：第一版機器人", en: "Project setup: a first bot", min: 20 },
    { slug: "i2-structured-answers", part: "intermediate", num: "I2", zh: "結構化回答與出處檢查", en: "Structured answers and citations", min: 20 },
    { slug: "i3-better-search", part: "intermediate", num: "I3", zh: "更好的搜尋，並量出差別", en: "Better search, measured", min: 25 },
    { slug: "i4-tools", part: "intermediate", num: "I4", zh: "工具呼叫：查個人資料", en: "Tool calls: personal data", min: 25 },
    { slug: "i5-memory-cost", part: "intermediate", num: "I5", zh: "對話記憶與成本", en: "Conversation memory and cost", min: 20 },
    { slug: "i6-testing", part: "intermediate", num: "I6", zh: "自動測試整個機器人", en: "Testing the whole bot", min: 20 },
    { slug: "i7-deploy", part: "intermediate", num: "I7", zh: "部署上線：做成網站", en: "Deploying as a website", min: 30 },
    { slug: "01-fde-role", part: "core", num: "01", zh: "FDE 是做什麼的", en: "What FDEs actually do", min: 15 },
    { slug: "02-engagement", part: "core", num: "02", zh: "從需求到上線的交付流程", en: "The engagement lifecycle", min: 20 },
    { slug: "03-ai-assisted-dev", part: "core", num: "03", zh: "與 Coding Agent 協作", en: "Working with coding agents", min: 25 },
    { slug: "04-structured-output", part: "core", num: "04", zh: "結構化輸出與資料契約", en: "Structured output and contracts", min: 25 },
    { slug: "05-retrieval", part: "core", num: "05", zh: "檢索與 RAG", en: "Retrieval and RAG", min: 35 },
    { slug: "06-agents", part: "core", num: "06", zh: "Agent、工具與人工審核", en: "Agents, tools and approvals", min: 35 },
    { slug: "07-evals", part: "core", num: "07", zh: "評測：把感覺變成數字", en: "Evals: from vibes to numbers", min: 30 },
    { slug: "08-production", part: "core", num: "08", zh: "上線：可觀測性、安全與成本", en: "Production: observability, security, cost", min: 30 },
    { slug: "09-labs", part: "core", num: "09", zh: "實作練習與延伸資源", en: "Labs and further reading", min: 15 }
  ];
  window.FDE_CHAPTERS = CHAPTERS;

  var T = {
    zh: { chapters: "章節", onThisPage: "本頁內容", progress: "學習進度", markDone: "標記為已讀完",
          done: "已讀完 ✓", prev: "上一章", next: "下一章", copy: "複製", copied: "已複製",
          home: "課程首頁", min: "分鐘", langBtn: "EN", langTitle: "Switch to English",
          themeLight: "切換為淺色", themeDark: "切換為深色", menu: "選單",
          correct: "答對了。", wrong: "再想想，看看下面的說明。", of: "/" },
    en: { chapters: "Chapters", onThisPage: "On this page", progress: "Progress", markDone: "Mark as complete",
          done: "Completed ✓", prev: "Previous", next: "Next", copy: "Copy", copied: "Copied",
          home: "Course home", min: "min", langBtn: "中文", langTitle: "切換為中文",
          themeLight: "Switch to light", themeDark: "Switch to dark", menu: "Menu",
          correct: "Correct.", wrong: "Not quite. See the explanation below.", of: "/" }
  };

  var root = document.documentElement;
  var page = root.getAttribute("data-page") || "";
  function lang() { return root.getAttribute("data-lang") === "en" ? "en" : "zh"; }
  function t(key) { return T[lang()][key]; }
  function store(key, value) { try { localStorage.setItem(key, value); } catch (e) { /* private mode */ } }
  function load(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  function el(tag, attrs, html) {
    var n = document.createElement(tag);
    if (attrs) Object.keys(attrs).forEach(function (k) { n.setAttribute(k, attrs[k]); });
    if (html != null) n.innerHTML = html;
    return n;
  }
  function both(zh, en) { return '<span lang="zh-Hant">' + zh + '</span><span lang="en">' + en + "</span>"; }

  // ---------------------------------------------------------------- progress
  function progress() {
    try { return JSON.parse(load("fde-progress") || "{}"); } catch (e) { return {}; }
  }
  function setDone(slug, value) {
    var p = progress();
    if (value) p[slug] = true; else delete p[slug];
    store("fde-progress", JSON.stringify(p));
    renderSidebar();
    document.dispatchEvent(new CustomEvent("fde-progress"));
  }
  window.FDE_PROGRESS = progress;

  // ---------------------------------------------------------------- title
  function applyTitle() {
    var title = root.getAttribute("data-title-" + lang());
    if (title) document.title = title;
  }

  // ---------------------------------------------------------------- top bar controls
  function updateControls() {
    var lb = document.getElementById("langBtn");
    if (lb) { lb.textContent = t("langBtn"); lb.title = t("langTitle"); lb.setAttribute("aria-label", t("langTitle")); }
    var tb = document.getElementById("themeBtn");
    if (tb) {
      var dark = effectiveTheme() === "dark";
      tb.textContent = dark ? "☀" : "☾";
      tb.title = dark ? t("themeLight") : t("themeDark");
      tb.setAttribute("aria-label", tb.title);
    }
    var mb = document.getElementById("menuBtn");
    if (mb) mb.setAttribute("aria-label", t("menu"));
  }
  function effectiveTheme() {
    var set = root.getAttribute("data-theme");
    if (set) return set;
    return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  function bindControls() {
    var lb = document.getElementById("langBtn");
    if (lb) lb.addEventListener("click", function () {
      var next = lang() === "en" ? "zh" : "en";
      root.setAttribute("data-lang", next);
      root.setAttribute("lang", next === "en" ? "en" : "zh-Hant");
      store("fde-lang", next);
      refreshText();
    });
    var tb = document.getElementById("themeBtn");
    if (tb) tb.addEventListener("click", function () {
      var next = effectiveTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      store("fde-theme", next);
      updateControls();
    });
    var mb = document.getElementById("menuBtn");
    if (mb) mb.addEventListener("click", function () {
      var open = document.body.classList.toggle("nav-open");
      mb.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("click", function (e) {
      if (!document.body.classList.contains("nav-open")) return;
      if (e.target.closest && (e.target.closest(".sidebar") || e.target.closest("#menuBtn"))) return;
      document.body.classList.remove("nav-open");
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") document.body.classList.remove("nav-open");
    });
  }

  // ---------------------------------------------------------------- sidebar
  function renderSidebar() {
    var nav = document.getElementById("sidebar");
    if (!nav) return;
    var p = progress();
    var doneCount = CHAPTERS.filter(function (c) { return p[c.slug]; }).length;
    var html = '<ol><li><a href="index.html"' + (page === "index" ? ' aria-current="page"' : "") +
      '><span class="num">·</span><span>' + both("課程首頁", "Course home") + "</span></a></li></ol>";
    var PARTS = [["basics", "入門篇", "Basics"], ["intermediate", "中級篇", "Intermediate"], ["core", "進階篇", "Core course"]];
    PARTS.forEach(function (part) {
      html += "<h2>" + both(part[1], part[2]) + "</h2><ol>";
      CHAPTERS.forEach(function (c) {
        if (c.part !== part[0]) return;
        html += '<li><a href="' + c.slug + '.html"' + (c.slug === page ? ' aria-current="page"' : "") + ">" +
          '<span class="num">' + c.num + "</span>" +
          "<span>" + both(c.zh, c.en) + "</span>" +
          (p[c.slug] ? '<span class="done" aria-label="done">✓</span>' : "<span></span>") + "</a></li>";
      });
      html += "</ol>";
    });
    html += '<ol style="margin-top:.8rem"><li><a href="projects.html"' + (page === "projects" ? ' aria-current="page"' : "") +
      '><span class="num">★</span><span>' + both("作品集專案", "Portfolio projects") + "</span><span></span></a></li>" +
      '<li><a href="certifications.html"' + (page === "certifications" ? ' aria-current="page"' : "") +
      '><span class="num">✓</span><span>' + both("認證與學習路線", "Certifications & path") + "</span><span></span></a></li>" +
      '<li><a href="glossary.html"' + (page === "glossary" ? ' aria-current="page"' : "") +
      '><span class="num">Aa</span><span>' + both("詞彙表", "Glossary") + "</span><span></span></a></li></ol>";
    var pct = Math.round(doneCount / CHAPTERS.length * 100);
    html += '<div class="progress">' + both("學習進度", "Progress") + " " + doneCount + " / " + CHAPTERS.length +
      '<div class="bar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="' + pct +
      '"><span style="width:' + pct + '%"></span></div></div>';
    nav.innerHTML = html;
  }

  // ---------------------------------------------------------------- toc
  var tocObserver;
  function renderToc() {
    var toc = document.getElementById("toc");
    var content = document.querySelector(".content");
    if (!toc || !content) return;
    var heads = Array.prototype.filter.call(content.querySelectorAll("h2"), function (h) {
      return !h.closest(".objectives, .quiz, .demo, .chapter-end");
    });
    heads.forEach(function (h, i) { if (!h.id) h.id = "s" + (i + 1); });
    if (heads.length < 2) { toc.innerHTML = ""; return; }
    var html = "<h2>" + t("onThisPage") + "</h2><ol>";
    heads.forEach(function (h) {
      var label = visibleText(h);
      html += '<li><a href="#' + h.id + '" data-target="' + h.id + '">' + escapeHtml(label) + "</a></li>";
    });
    toc.innerHTML = html + "</ol>";
    if (tocObserver) tocObserver.disconnect();
    if (!("IntersectionObserver" in window)) return;
    tocObserver = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (!en.isIntersecting) return;
        toc.querySelectorAll("a").forEach(function (a) { a.classList.toggle("active", a.dataset.target === en.target.id); });
      });
    }, { rootMargin: "-70px 0px -70% 0px" });
    heads.forEach(function (h) { tocObserver.observe(h); });
  }
  function visibleText(node) {
    var hiddenLang = lang() === "en" ? "zh-Hant" : "en";
    var clone = node.cloneNode(true);
    clone.querySelectorAll('[lang="' + hiddenLang + '"]').forEach(function (n) { n.remove(); });
    return clone.textContent.trim();
  }
  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }
  window.FDE_ESCAPE = escapeHtml;

  // ---------------------------------------------------------------- chapter footer
  function renderChapterEnd() {
    var idx = CHAPTERS.findIndex(function (c) { return c.slug === page; });
    var article = document.querySelector(".content");
    if (idx < 0 || !article) return;
    var end = document.getElementById("chapterEnd") || article.appendChild(el("footer", { id: "chapterEnd", class: "chapter-end" }));
    var isDone = !!progress()[page];
    var prev = CHAPTERS[idx - 1], next = CHAPTERS[idx + 1];
    end.innerHTML =
      '<div class="complete-row"><button class="btn ' + (isDone ? "" : "primary") + '" id="doneBtn" type="button">' +
      (isDone ? t("done") : t("markDone")) + "</button></div>" +
      '<nav class="pager" aria-label="pagination">' +
      (prev ? '<a class="prev" href="' + prev.slug + '.html"><small>← ' + t("prev") + "</small>" + both(prev.zh, prev.en) + "</a>" : "<span></span>") +
      (next ? '<a class="next" href="' + next.slug + '.html"><small>' + t("next") + " →</small>" + both(next.zh, next.en) + "</a>" :
              '<a class="next" href="index.html"><small>' + t("home") + " →</small>" + both("回到課程首頁", "Back to the course home") + "</a>") +
      "</nav>";
    document.getElementById("doneBtn").addEventListener("click", function () {
      setDone(page, !progress()[page]);
      renderChapterEnd();
    });
  }

  // ---------------------------------------------------------------- code blocks
  function enhanceCode() {
    document.querySelectorAll("figure.code").forEach(function (fig) {
      var cap = fig.querySelector("figcaption");
      if (!cap) { cap = el("figcaption", null, "<span></span>"); fig.insertBefore(cap, fig.firstChild); }
      if (cap.querySelector(".copy-btn")) return;
      var btn = el("button", { type: "button", class: "copy-btn" }, t("copy"));
      btn.addEventListener("click", function () {
        var code = fig.querySelector("pre").innerText;
        var finish = function () { btn.textContent = t("copied"); setTimeout(function () { btn.textContent = t("copy"); }, 1500); };
        if (navigator.clipboard) navigator.clipboard.writeText(code).then(finish, function () {});
      });
      cap.appendChild(btn);
    });
    if (window.hljs) {
      document.querySelectorAll('pre code[class*="language-"]').forEach(function (c) {
        if (!c.dataset.highlighted) window.hljs.highlightElement(c);
      });
    }
  }

  // ---------------------------------------------------------------- quizzes
  function bindQuizzes() {
    document.querySelectorAll("[data-quiz] fieldset").forEach(function (fs) {
      var answer = fs.getAttribute("data-answer");
      fs.addEventListener("change", function (e) {
        if (e.target.type !== "radio") return;
        fs.classList.add("answered");
        fs.querySelectorAll("label").forEach(function (l) {
          var input = l.querySelector("input");
          l.classList.remove("correct", "wrong");
          if (input.value === answer) l.classList.add("correct");
          else if (input.checked) l.classList.add("wrong");
        });
        var res = fs.querySelector(".result") || fs.querySelector(".explain").insertAdjacentElement("beforebegin", el("div", { class: "result", role: "status" }));
        res.dataset.ok = String(e.target.value === answer);
        res.innerHTML = e.target.value === answer ? both("答對了。", "Correct.") : both("再想想，看看下面的說明。", "Not quite. See the explanation below.");
      });
    });
  }

  // ---------------------------------------------------------------- refresh on language change
  function refreshText() {
    applyTitle();
    updateControls();
    renderToc();
    renderChapterEnd();
    document.querySelectorAll(".copy-btn").forEach(function (b) { b.textContent = t("copy"); });
    document.dispatchEvent(new CustomEvent("fde-lang", { detail: lang() }));
  }
  window.FDE_LANG = lang;

  function init() {
    applyTitle();
    bindControls();
    updateControls();
    renderSidebar();
    renderToc();
    renderChapterEnd();
    enhanceCode();
    bindQuizzes();
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
})();
