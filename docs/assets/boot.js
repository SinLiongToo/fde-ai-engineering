// 在畫面繪製前決定語言與主題，避免閃爍。/ Decide language and theme before first paint.
(function () {
  var root = document.documentElement;
  function read(key) { try { return localStorage.getItem(key); } catch (e) { return null; } }
  var params = new URLSearchParams(location.search);
  var lang = params.get("lang") || read("fde-lang") ||
    ((navigator.language || "").toLowerCase().indexOf("zh") === 0 ? "zh" : "en");
  if (lang !== "en") lang = "zh";
  root.setAttribute("data-lang", lang);
  root.setAttribute("lang", lang === "en" ? "en" : "zh-Hant");
  var theme = read("fde-theme");
  if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
})();
