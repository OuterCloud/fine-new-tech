/* ── State ── */
let activeDate = null;
let activeResearch = null; // {date, id} — 当前查看的调研报告
let langMode = "zh";
let reportsMetadata = {};
let viewMode = "none"; // "none" | "report" | "research"
let pagesBaseUrl = ""; // GitHub Pages base URL

/* ── Init ── */
document.addEventListener("DOMContentLoaded", () => {
  loadReportList();
  loadResearchList();
  loadPagesUrl();
  handleHashRoute();
});

/* ── Hash 路由 ── */
function setHash(hash) {
  history.replaceState(null, "", hash);
}

function handleHashRoute() {
  const hash = location.hash;
  if (hash === "#settings") {
    showSettings();
  } else if (hash.startsWith("#report/")) {
    const date = hash.slice(8);
    if (date) loadReport(date, langMode);
  } else if (hash.startsWith("#research/")) {
    const parts = hash.slice(10).split("/");
    if (parts.length === 2) loadResearch(parts[0], parts[1]);
  }
}

window.addEventListener("hashchange", handleHashRoute);

async function loadPagesUrl() {
  try {
    const res = await fetch("/api/pages-url");
    const data = await res.json();
    pagesBaseUrl = data.url || "";
  } catch {
    pagesBaseUrl = "";
  }
}

function updatePagesLink() {
  const link = document.getElementById("toolbar-pages-link");
  if (!pagesBaseUrl) {
    link.classList.add("hidden");
    return;
  }
  // Jekyll URL 格式: /YYYY/MM/DD/slug/
  let postUrl = "";
  if (viewMode === "report" && activeDate) {
    const parts = activeDate.split("-");
    postUrl = `${pagesBaseUrl}${parts[0]}/${parts[1]}/${parts[2]}/${langMode}/`;
  } else if (viewMode === "research" && activeResearch) {
    const parts = activeResearch.date.split("-");
    postUrl = `${pagesBaseUrl}${parts[0]}/${parts[1]}/${parts[2]}/${activeResearch.id}/`;
  }
  if (postUrl) {
    link.href = postUrl;
    link.classList.remove("hidden");
  } else {
    link.classList.add("hidden");
  }
}

/* ══════════════════════════════════════════════════════════
   每日脉搏报告
   ══════════════════════════════════════════════════════════ */

async function loadReportList() {
  try {
    const res = await fetch("/api/reports");
    const reports = await res.json();
    reportsMetadata = {};
    for (const r of reports) reportsMetadata[r.date] = r;
    renderReportList(reports);
  } catch (err) {
    console.error("Failed to load report list:", err);
  }
}

function renderReportList(reports) {
  const ul = document.getElementById("report-list");
  ul.innerHTML = "";
  if (reports.length === 0) {
    ul.innerHTML = '<li class="empty-hint">暂无简报</li>';
    return;
  }
  for (const r of reports) {
    const li = document.createElement("li");
    if (viewMode === "report" && r.date === activeDate)
      li.classList.add("active");
    const row = document.createElement("div");
    row.className = "report-row";
    const a = document.createElement("a");
    a.href = "#";
    a.onclick = (e) => {
      e.preventDefault();
      loadReport(r.date, langMode);
    };
    const dateSpan = document.createElement("span");
    dateSpan.textContent = r.date;
    const badge = document.createElement("span");
    badge.className = "size-badge";
    badge.textContent = r.size_kb + " KB";
    a.appendChild(dateSpan);
    a.appendChild(badge);
    const delBtn = document.createElement("button");
    delBtn.className = "list-delete-btn";
    delBtn.title = "删除";
    delBtn.textContent = "×";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      deleteReport(r.date);
    };
    row.appendChild(a);
    row.appendChild(delBtn);
    li.appendChild(row);
    ul.appendChild(li);
  }
}

async function loadReport(dateStr, lang) {
  activeDate = dateStr;
  activeResearch = null;
  viewMode = "report";
  setHash(`#report/${dateStr}`);
  const effectiveLang = lang || langMode;
  refreshAllListHighlights();
  try {
    const res = await fetch(`/api/reports/${dateStr}?lang=${effectiveLang}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    langMode = data.lang;
    showReport(data.content);
  } catch (err) {
    showError(`加载报告失败: ${err.message}`);
  }
}

function showReport(markdown) {
  document.getElementById("welcome").classList.add("hidden");
  document.getElementById("research-content").classList.add("hidden");
  document.getElementById("research-section").classList.add("hidden");
  document.getElementById("settings-page").classList.add("hidden");
  const toolbar = document.getElementById("report-toolbar");
  toolbar.classList.remove("hidden");
  document.getElementById("toolbar-date").textContent = activeDate || "";
  // 显示语言切换和重新生成（仅每日简报有）
  document.getElementById("lang-switch").classList.remove("hidden");
  document.getElementById("regenerate-btn").classList.remove("hidden");
  updateLangButtons();
  setActionBtnsDisabled(false);
  const el = document.getElementById("report-content");
  el.classList.remove("hidden");
  el.innerHTML = marked.parse(markdown);
  // 显示追问修订框
  document.getElementById("refine-section").classList.remove("hidden");
  document.getElementById("refine-input").value = "";
  updatePagesLink();
  document.getElementById("main").scrollTop = 0;
}

function showError(msg) {
  document.getElementById("welcome").classList.add("hidden");
  document.getElementById("report-toolbar").classList.add("hidden");
  document.getElementById("research-content").classList.add("hidden");
  document.getElementById("refine-section").classList.add("hidden");
  document.getElementById("research-section").classList.add("hidden");
  document.getElementById("settings-page").classList.add("hidden");
  const el = document.getElementById("report-content");
  el.classList.remove("hidden");
  el.innerHTML = `<p style="color:#cf222e;padding:16px;">${msg}</p>`;
}

async function switchLang(lang) {
  if (!activeDate || lang === langMode) return;
  langMode = lang;
  await loadReport(activeDate, lang);
}

function updateLangButtons() {
  const meta = reportsMetadata[activeDate] || {};
  const zhBtn = document.getElementById("lang-zh-btn");
  const enBtn = document.getElementById("lang-en-btn");
  if (!zhBtn || !enBtn) return;
  zhBtn.classList.toggle("active", langMode === "zh");
  enBtn.classList.toggle("active", langMode === "en");
  enBtn.disabled = !meta.has_en;
  enBtn.title = meta.has_en ? "" : "该报告暂无英文版，请重新生成";
}

async function deleteReport(dateStr) {
  const target = dateStr || activeDate;
  if (!target) return;
  if (!confirm(`确定删除 ${target} 的报告？此操作不可撤销。`)) return;
  try {
    const res = await fetch(`/api/reports/${target}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (target === activeDate && viewMode === "report") {
      resetToWelcome();
    }
    await loadReportList();
  } catch (err) {
    alert(`删除失败: ${err.message}`);
  }
}

async function regenerateReport() {
  if (!activeDate) return;
  if (
    !confirm(
      `重新生成 ${activeDate} 的报告？将重新抓取所有数据源并覆盖现有报告。`,
    )
  )
    return;
  await runGenerate(activeDate, true);
}

async function generateReport() {
  await runGenerate(null, false);
}

/* ══════════════════════════════════════════════════════════
   调研报告
   ══════════════════════════════════════════════════════════ */

async function loadResearchList() {
  try {
    const res = await fetch("/api/researches");
    const items = await res.json();
    renderResearchList(items);
  } catch (err) {
    console.error("Failed to load research list:", err);
  }
}

function renderResearchList(items) {
  const ul = document.getElementById("research-list");
  ul.innerHTML = "";
  if (items.length === 0) {
    ul.innerHTML = '<li class="empty-hint">暂无调研</li>';
    return;
  }
  for (const r of items) {
    const li = document.createElement("li");
    if (
      viewMode === "research" &&
      activeResearch &&
      activeResearch.id === r.id &&
      activeResearch.date === r.date
    ) {
      li.classList.add("active");
    }
    const row = document.createElement("div");
    row.className = "report-row";
    const a = document.createElement("a");
    a.href = "#";
    a.onclick = (e) => {
      e.preventDefault();
      loadResearch(r.date, r.id);
    };
    const topicSpan = document.createElement("span");
    topicSpan.className = "research-topic-text";
    topicSpan.textContent =
      r.topic.length > 24 ? r.topic.slice(0, 24) + "…" : r.topic;
    topicSpan.title = r.topic;
    const badge = document.createElement("span");
    badge.className = "size-badge";
    badge.textContent = r.size_kb + " KB";
    a.appendChild(topicSpan);
    a.appendChild(badge);
    const delBtn = document.createElement("button");
    delBtn.className = "list-delete-btn";
    delBtn.title = "删除";
    delBtn.textContent = "×";
    delBtn.onclick = (e) => {
      e.stopPropagation();
      deleteResearch(r.date, r.id);
    };
    row.appendChild(a);
    row.appendChild(delBtn);
    li.appendChild(row);
    ul.appendChild(li);
  }
}

async function loadResearch(dateStr, researchId) {
  activeResearch = { date: dateStr, id: researchId };
  activeDate = null;
  viewMode = "research";
  setHash(`#research/${dateStr}/${researchId}`);
  refreshAllListHighlights();
  try {
    const res = await fetch(`/api/researches/${dateStr}/${researchId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    showResearchReport(data.content, dateStr, researchId);
  } catch (err) {
    showError(`加载调研报告失败: ${err.message}`);
  }
}

function showResearchReport(markdown, dateStr, researchId) {
  document.getElementById("welcome").classList.add("hidden");
  document.getElementById("research-content").classList.add("hidden");
  document.getElementById("research-section").classList.add("hidden");
  document.getElementById("settings-page").classList.add("hidden");
  // 复用 report-toolbar，但隐藏语言切换和重新生成
  const toolbar = document.getElementById("report-toolbar");
  toolbar.classList.remove("hidden");
  document.getElementById("toolbar-date").textContent = `${dateStr} · 调研`;
  document.getElementById("lang-switch").classList.add("hidden");
  document.getElementById("regenerate-btn").classList.add("hidden");
  setActionBtnsDisabled(false);
  const el = document.getElementById("report-content");
  el.classList.remove("hidden");
  el.innerHTML = marked.parse(markdown);
  // 显示追问修订区域
  document.getElementById("refine-section").classList.remove("hidden");
  document.getElementById("refine-input").value = "";
  updatePagesLink();
  document.getElementById("main").scrollTop = 0;
}

async function deleteResearch(dateStr, researchId) {
  if (!confirm("确定删除此调研报告？")) return;
  try {
    const res = await fetch(`/api/researches/${dateStr}/${researchId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    if (
      viewMode === "research" &&
      activeResearch &&
      activeResearch.id === researchId
    ) {
      resetToWelcome();
    }
    await loadResearchList();
  } catch (err) {
    alert(`删除失败: ${err.message}`);
  }
}

/* ══════════════════════════════════════════════════════════
   公共函数
   ══════════════════════════════════════════════════════════ */

function resetToWelcome() {
  activeDate = null;
  activeResearch = null;
  viewMode = "none";
  setHash("#");
  document.getElementById("report-toolbar").classList.add("hidden");
  document.getElementById("report-content").classList.add("hidden");
  document.getElementById("research-content").classList.add("hidden");
  document.getElementById("refine-section").classList.add("hidden");
  document.getElementById("settings-page").classList.add("hidden");
  document.getElementById("research-section").classList.remove("hidden");
  document.getElementById("welcome").classList.remove("hidden");
  refreshAllListHighlights();
}

function refreshAllListHighlights() {
  // 简报列表
  document.querySelectorAll("#report-list li").forEach((li) => {
    const dateText = li.querySelector("a span:first-child")?.textContent;
    li.classList.toggle(
      "active",
      viewMode === "report" && dateText === activeDate,
    );
  });
  // 调研列表
  document.querySelectorAll("#research-list li").forEach((li) => {
    li.classList.remove("active");
  });
  if (viewMode === "research" && activeResearch) {
    // 重新渲染会处理高亮，这里做简单匹配
    loadResearchList();
  }
}

function setActionBtnsDisabled(disabled) {
  [
    "regenerate-btn",
    "delete-btn",
    "toolbar-publish-btn",
    "lang-zh-btn",
    "lang-en-btn",
  ].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = disabled;
  });
}

/* ── 删除按钮（toolbar）—— 根据当前视图决定删除什么 ── */
async function handleToolbarDelete() {
  if (viewMode === "report" && activeDate) {
    await deleteReport(activeDate);
  } else if (viewMode === "research" && activeResearch) {
    await deleteResearch(activeResearch.date, activeResearch.id);
  }
}

/* ══════════════════════════════════════════════════════════
   发布到 GitHub Pages
   ══════════════════════════════════════════════════════════ */

async function publishToGitHub() {
  const publishBtn = document.getElementById("publish-btn");
  const toolbarPublishBtn = document.getElementById("toolbar-publish-btn");
  const progress = document.getElementById("progress");
  const progressFill = document.getElementById("progress-fill");
  const progressStatus = document.getElementById("progress-status");

  publishBtn.disabled = true;
  if (toolbarPublishBtn) toolbarPublishBtn.disabled = true;
  progress.classList.remove("hidden");
  progressFill.style.width = "10%";
  progressStatus.textContent = "正在连接 GitHub...";

  try {
    const response = await fetch("/api/publish", { method: "POST" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let event;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (event.status === "cloning") {
          progressFill.style.width = "20%";
          progressStatus.textContent = event.message || "克隆/拉取仓库...";
        } else if (event.status === "initializing") {
          progressFill.style.width = "40%";
          progressStatus.textContent = "初始化 Jekyll 站点...";
        } else if (event.status === "copying") {
          progressFill.style.width = "65%";
          progressStatus.textContent = `转换报告（新增 ${event.new}，跳过 ${event.skip}）...`;
        } else if (event.status === "pushing") {
          progressFill.style.width = "85%";
          progressStatus.textContent = "推送到 GitHub...";
        } else if (event.status === "complete") {
          progressFill.style.width = "100%";
          if (event.new === 0) {
            progressStatus.textContent = "所有报告已是最新，无需推送。";
          } else {
            const urlHtml = event.url
              ? `，<a href="${event.url}" target="_blank">点击访问</a>`
              : "";
            progressStatus.innerHTML = `发布成功（${event.new} 篇）${urlHtml}`;
          }
        } else if (event.status === "error") {
          throw new Error(event.message);
        }
      }
    }
  } catch (err) {
    progressStatus.textContent = `发布失败: ${err.message}`;
    progressFill.style.background = "#cf222e";
  } finally {
    publishBtn.disabled = false;
    if (toolbarPublishBtn) toolbarPublishBtn.disabled = false;
    setTimeout(() => {
      progress.classList.add("hidden");
      progressFill.style.width = "0%";
      progressFill.style.background = "";
      progressStatus.innerHTML = "";
    }, 5000);
  }
}

/* ══════════════════════════════════════════════════════════
   生成每日脉搏报告（SSE）
   ══════════════════════════════════════════════════════════ */

async function runGenerate(dateStr, force) {
  const btn = document.getElementById("generate-btn");
  const btnText = document.getElementById("generate-btn-text");
  const progress = document.getElementById("progress");
  const progressFill = document.getElementById("progress-fill");
  const progressStatus = document.getElementById("progress-status");

  btn.disabled = true;
  btnText.textContent = "生成中...";
  setActionBtnsDisabled(true);
  progress.classList.remove("hidden");
  progressFill.style.width = "5%";
  progressStatus.textContent = "正在启动...";

  const sourceLabels = {
    finance_news: "财经新闻",
    github_trending: "GitHub Trending",
    hacker_news: "Hacker News",
    arxiv: "arXiv 论文",
    product_hunt: "Product Hunt",
  };
  const stepsTotal = 7;
  let stepsDone = 0;
  function advance(label) {
    stepsDone++;
    progressFill.style.width = `${Math.round((stepsDone / stepsTotal) * 100)}%`;
    progressStatus.textContent = label;
  }

  try {
    const params = new URLSearchParams();
    if (force) params.set("force", "true");
    if (dateStr) params.set("date", dateStr);
    const response = await fetch(`/api/generate?${params}`, { method: "POST" });
    if (!response.ok)
      throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let event;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (event.status === "fetching") {
          advance(`正在获取 ${sourceLabels[event.source] || event.source}...`);
        } else if (event.status === "summarizing") {
          advance("正在生成中英双语报告（并行调用 AI）...");
        } else if (event.status === "complete") {
          advance("完成！");
          await loadReportList();
          await loadReport(event.date, langMode);
        } else if (event.status === "error") {
          throw new Error(event.message);
        }
      }
    }
  } catch (err) {
    progressStatus.textContent = `错误: ${err.message}`;
    progressFill.style.background = "#cf222e";
  } finally {
    btn.disabled = false;
    btnText.textContent = "生成今日简报";
    setActionBtnsDisabled(false);
    setTimeout(() => {
      progress.classList.add("hidden");
      progressFill.style.width = "0%";
      progressFill.style.background = "";
      progressStatus.textContent = "";
    }, 3000);
  }
}

/* ══════════════════════════════════════════════════════════
   自定义调研（SSE 流式）
   ══════════════════════════════════════════════════════════ */

async function startResearch() {
  const input = document.getElementById("research-input");
  const topic = input.value.trim();
  if (!topic) {
    input.focus();
    return;
  }

  const btn = document.getElementById("research-btn");
  const btnText = document.getElementById("research-btn-text");
  const progress = document.getElementById("research-progress");
  const progressFill = document.getElementById("research-progress-fill");
  const progressStatus = document.getElementById("research-progress-status");
  const contentEl = document.getElementById("research-content");

  // 切换到调研流式视图
  document.getElementById("welcome").classList.add("hidden");
  document.getElementById("report-toolbar").classList.add("hidden");
  document.getElementById("report-content").classList.add("hidden");
  document.getElementById("refine-section").classList.add("hidden");
  document.getElementById("research-section").classList.add("hidden");
  document.getElementById("settings-page").classList.add("hidden");
  contentEl.classList.remove("hidden");
  contentEl.innerHTML =
    '<p style="color:#57606a;padding:8px;">正在准备调研...</p>';

  viewMode = "research";
  activeDate = null;
  activeResearch = null;

  btn.disabled = true;
  btnText.textContent = "调研中...";
  progress.classList.remove("hidden");
  progressFill.style.width = "100%";
  progressStatus.textContent = `正在对「${topic.slice(0, 30)}${
    topic.length > 30 ? "..." : ""
  }」展开深度调研...`;

  try {
    const response = await fetch("/api/research", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic }),
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${response.status}`);
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullContent = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let event;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (event.status === "streaming") {
          fullContent += event.chunk;
          contentEl.innerHTML = marked.parse(fullContent);
          const main = document.getElementById("main");
          main.scrollTop = main.scrollHeight;
        } else if (event.status === "complete") {
          progressStatus.textContent = `调研完成，已保存 (${(
            event.total_length / 1000
          ).toFixed(1)}K 字)`;
          progressFill.style.animation = "none";
          // 刷新调研列表并高亮新报告
          await loadResearchList();
          if (event.date && event.research_id) {
            activeResearch = { date: event.date, id: event.research_id };
            // 切换到正式视图（toolbar + 追问框）
            document.getElementById("research-content").classList.add("hidden");
            showResearchReport(fullContent, event.date, event.research_id);
          }
        } else if (event.status === "error") {
          throw new Error(event.message);
        }
      }
    }
  } catch (err) {
    progressStatus.textContent = `调研失败: ${err.message}`;
    progressFill.style.background = "#cf222e";
    progressFill.style.animation = "none";
    if (!contentEl.innerHTML.includes("调研报告")) {
      contentEl.innerHTML = `<p style="color:#cf222e;padding:16px;">调研失败: ${err.message}</p>`;
    }
  } finally {
    btn.disabled = false;
    btnText.textContent = "开始调研";
    setTimeout(() => {
      progress.classList.add("hidden");
      progressFill.style.width = "0%";
      progressFill.style.background = "";
      progressFill.style.animation = "";
      progressStatus.textContent = "";
    }, 4000);
  }
}

// Ctrl+Enter / Cmd+Enter 快捷键
document.addEventListener("DOMContentLoaded", () => {
  const input = document.getElementById("research-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        startResearch();
      }
    });
  }
});

/* ══════════════════════════════════════════════════════════
   追问修订调研报告
   ══════════════════════════════════════════════════════════ */

async function startRefine() {
  // 支持简报和调研两种模式
  if (viewMode !== "report" && viewMode !== "research") return;
  if (viewMode === "research" && !activeResearch) return;
  if (viewMode === "report" && !activeDate) return;

  const input = document.getElementById("refine-input");
  const feedback = input.value.trim();
  if (!feedback) {
    input.focus();
    return;
  }

  const btn = document.getElementById("refine-btn");
  const btnText = document.getElementById("refine-btn-text");
  const progress = document.getElementById("refine-progress");
  const progressFill = document.getElementById("refine-progress-fill");
  const progressStatus = document.getElementById("refine-progress-status");
  const contentEl = document.getElementById("report-content");

  btn.disabled = true;
  btnText.textContent = "修订中...";
  progress.classList.remove("hidden");
  progressFill.style.width = "100%";
  progressStatus.textContent = "AI 正在根据你的反馈修订报告...";

  // 根据视图模式选择接口和参数
  let url, body;
  if (viewMode === "research") {
    url = "/api/research/refine";
    body = {
      date: activeResearch.date,
      research_id: activeResearch.id,
      feedback,
    };
  } else {
    url = "/api/reports/refine";
    body = { date: activeDate, lang: langMode, feedback };
  }

  try {
    const response = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!response.ok) {
      const errData = await response.json().catch(() => ({}));
      throw new Error(errData.detail || `HTTP ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let fullContent = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        let event;
        try {
          event = JSON.parse(line.slice(6));
        } catch {
          continue;
        }
        if (event.status === "streaming") {
          fullContent += event.chunk;
          contentEl.innerHTML = marked.parse(fullContent);
          const main = document.getElementById("main");
          main.scrollTop = main.scrollHeight;
        } else if (event.status === "complete") {
          progressStatus.textContent = `修订完成，已保存 (${(
            event.total_length / 1000
          ).toFixed(1)}K 字)`;
          progressFill.style.animation = "none";
          input.value = "";
          if (viewMode === "research") {
            await loadResearchList();
          } else {
            await loadReportList();
          }
        } else if (event.status === "error") {
          throw new Error(event.message);
        }
      }
    }
  } catch (err) {
    progressStatus.textContent = `修订失败: ${err.message}`;
    progressFill.style.background = "#cf222e";
    progressFill.style.animation = "none";
  } finally {
    btn.disabled = false;
    btnText.textContent = "修订";
    setTimeout(() => {
      progress.classList.add("hidden");
      progressFill.style.width = "0%";
      progressFill.style.background = "";
      progressFill.style.animation = "";
      progressStatus.textContent = "";
    }, 4000);
  }
}

// 追问输入框也支持 Ctrl+Enter / Cmd+Enter
document.addEventListener("DOMContentLoaded", () => {
  const refineInput = document.getElementById("refine-input");
  if (refineInput) {
    refineInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        startRefine();
      }
    });
  }
});

/* ══════════════════════════════════════════════════════════
   设置页面
   ══════════════════════════════════════════════════════════ */

async function showSettings() {
  // 隐藏其他视图
  document.getElementById("welcome").classList.add("hidden");
  document.getElementById("research-section").classList.add("hidden");
  document.getElementById("report-toolbar").classList.add("hidden");
  document.getElementById("report-content").classList.add("hidden");
  document.getElementById("research-content").classList.add("hidden");
  document.getElementById("refine-section").classList.add("hidden");
  document.getElementById("settings-page").classList.remove("hidden");
  document.getElementById("settings-msg").textContent = "";

  viewMode = "settings";
  activeDate = null;
  activeResearch = null;
  setHash("#settings");
  refreshAllListHighlights();

  try {
    const res = await fetch("/api/settings");
    const fields = await res.json();
    renderSettingsForm(fields);
  } catch (err) {
    document.getElementById(
      "settings-form",
    ).innerHTML = `<p style="color:#cf222e;">加载配置失败: ${err.message}</p>`;
  }
}

function renderSettingsForm(fields) {
  const form = document.getElementById("settings-form");
  form.innerHTML = "";
  let currentGroup = "";

  for (const f of fields) {
    if (f.group !== currentGroup) {
      currentGroup = f.group;
      const groupDiv = document.createElement("div");
      groupDiv.className = "settings-group";
      const groupLabel = document.createElement("div");
      groupLabel.className = "settings-group-label";
      groupLabel.textContent = currentGroup;
      groupDiv.appendChild(groupLabel);
      form.appendChild(groupDiv);
    }

    const lastGroup = form.lastElementChild;
    const row = document.createElement("div");
    row.className = "settings-field";

    const label = document.createElement("label");
    label.textContent = f.label;
    label.setAttribute("for", `setting-${f.key}`);

    if (f.hint) {
      const tip = document.createElement("span");
      tip.className = "settings-hint";
      tip.textContent = "?";
      tip.title = f.hint;
      label.appendChild(tip);
    }

    const input = document.createElement("input");
    input.type = f.sensitive ? "password" : "text";
    input.id = `setting-${f.key}`;
    input.name = f.key;
    input.value = f.value;
    input.placeholder = f.sensitive ? "留空则不修改" : "";

    row.appendChild(label);
    row.appendChild(input);
    lastGroup.appendChild(row);
  }
}

async function saveSettings() {
  const form = document.getElementById("settings-form");
  const inputs = form.querySelectorAll("input");
  const data = {};
  inputs.forEach((input) => {
    data[input.name] = input.value;
  });

  const msg = document.getElementById("settings-msg");
  const btn = document.getElementById("settings-save-btn");
  btn.disabled = true;

  try {
    const res = await fetch("/api/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${res.status}`);
    }
    msg.style.color = "#1a7f37";
    msg.textContent = "保存成功，配置已生效";
  } catch (err) {
    msg.style.color = "#cf222e";
    msg.textContent = `保存失败: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
}
