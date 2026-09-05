const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let notebookId = "";
let imageData = "";
let lastSavedId = "";
let ingestBusy = false;
let stream = null;
let bankItems = [];
let quizQueue = [];
let quizIndex = 0;
let revealed = false;

const statsEl = $("#stats");
const listEl = $("#list");
const quizEl = $("#quiz");
const preview = $("#preview");
const video = $("#camera");
const canvas = $("#shot");

function isLocalHost() {
  return ["127.0.0.1", "localhost"].includes(location.hostname);
}

function api(path, query) {
  const qs = query ? "?" + new URLSearchParams(query).toString() : "";
  return `/api/n/${notebookId}${path}${qs}`;
}

function imgUrl(name) {
  return `/api/n/${notebookId}/images/${name}`;
}

function shareUrl() {
  const u = new URL(location.href);
  u.searchParams.set("n", notebookId);
  return u.toString();
}

function renderShare() {
  const line = $("#shareLine");
  if (!notebookId) return;
  line.innerHTML = `专属链接（收藏或发给家人，不要发到公开群）：<br><code></code> <button type="button" class="ghost" id="btnCopy">复制</button>`;
  line.querySelector("code").textContent = shareUrl();
  if (isLocalHost()) {
    const tip = document.createElement("span");
    tip.textContent = " 局域网请把 127.0.0.1 换成启动窗口里的电脑 IP。";
    line.appendChild(tip);
  }
  $("#btnCopy").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(shareUrl());
      $("#btnCopy").textContent = "已复制";
    } catch (e) {
      prompt("复制这个链接", shareUrl());
    }
  });
}

async function ensureNotebook() {
  const params = new URLSearchParams(location.search);
  const fromUrl = params.get("n") || "";
  const fromStore = localStorage.getItem("wqNotebook") || "";
  if (fromUrl) {
    notebookId = fromUrl;
  } else if (fromStore) {
    notebookId = fromStore;
  } else if (isLocalHost()) {
    notebookId = "local";
  } else {
    const res = await fetch("/api/notebooks", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "无法创建错题本");
    notebookId = data.id;
  }
  localStorage.setItem("wqNotebook", notebookId);
  const u = new URL(location.href);
  if (u.searchParams.get("n") !== notebookId) {
    u.searchParams.set("n", notebookId);
    history.replaceState({}, "", u);
  }
  renderShare();
}

$$(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    $$(".tab").forEach((b) => b.classList.remove("active"));
    $$(".panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    $("#" + btn.dataset.tab).classList.add("active");
    if (btn.dataset.tab === "library") loadBank();
  });
});

function renderStats(stats) {
  if (!stats) return;
  const subjects = Object.entries(stats.subjects || {})
    .map(([k, v]) => `${k} ${v}`)
    .join(" · ");
  statsEl.innerHTML = `
    <span>题库 ${stats.total || 0}</span>
    <span>待练 ${stats.due || 0}</span>
    ${subjects ? `<span>${subjects}</span>` : ""}
  `;
}

async function loadBank() {
  const res = await fetch(api("/bank"));
  const data = await res.json();
  bankItems = data.items || [];
  renderStats(data.stats);
  renderList();
}

function renderList() {
  const subject = $("#filterSubject").value.trim();
  const q = $("#search").value.trim().toLowerCase();
  const items = bankItems.filter((it) => {
    if (subject && it.subject !== subject) return false;
    const blob = `${it.stem} ${it.knowledge} ${it.explanation} ${(it.tags || []).join(" ")}`.toLowerCase();
    return !q || blob.includes(q);
  });
  if (!items.length) {
    listEl.innerHTML = `<div class="card">还没有符合条件的错题。</div>`;
    return;
  }
  listEl.innerHTML = items.map((it) => `
    <article class="card item">
      ${it.imageFile
        ? `<img src="${imgUrl(it.imageFile)}" alt="错题图片" />`
        : `<div class="thumb-empty">无图</div>`}
      <div>
        <p class="meta">${escapeHtml(it.subject || "未分类")} · ${escapeHtml(it.source || "未注明来源")} · 错${it.wrongCount || 0}/对${it.correctCount || 0}</p>
        <p class="stem">${escapeHtml(practiceStem(it))}</p>
        <div class="tags">
          ${(it.tags || []).map((t) => `<span class="tag">${escapeHtml(t)}</span>`).join("")}
          ${it.knowledge ? `<span class="tag">${escapeHtml(it.knowledge)}</span>` : ""}
        </div>
        <button class="danger" data-del="${it.id}">删除</button>
      </div>
    </article>
  `).join("");
  listEl.querySelectorAll("[data-del]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      if (!confirm("删除这道错题？")) return;
      await fetch(api("/items/" + btn.dataset.del), { method: "DELETE" });
      loadBank();
    });
  });
}

$("#filterSubject").addEventListener("input", renderList);
$("#search").addEventListener("input", renderList);

function showSaveOk(text) {
  const top = $("#ingestStatus");
  if (top) {
    top.hidden = false;
    top.textContent = text;
  }
  const ok = $("#form").querySelector(".save-ok");
  if (ok) {
    ok.hidden = false;
    ok.textContent = text;
  }
}

async function fetchJson(url, options, timeoutMs) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs || 60000);
  try {
    const res = await fetch(url, Object.assign({}, options, { signal: ctrl.signal }));
    const data = await res.json();
    return data;
  } catch (err) {
    if (err && err.name === "AbortError") {
      throw new Error("请求超时，请换一张更清晰的图再试");
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function compressFile(file) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    img.onload = () => {
      const max = 1600;
      let w = img.width;
      let h = img.height;
      if (Math.max(w, h) > max) {
        const scale = max / Math.max(w, h);
        w = Math.round(w * scale);
        h = Math.round(h * scale);
      }
      canvas.width = w;
      canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      resolve(canvas.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("无法读取图片"));
    };
    img.src = url;
  });
}

async function saveItem(extra) {
  const fd = new FormData($("#form"));
  const options = String(fd.get("options") || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  const tags = String(fd.get("tags") || "")
    .split(/[,，]/)
    .map((x) => x.trim())
    .filter(Boolean);
  extra = extra || {};
  const stem = String((extra && extra.stem) || fd.get("stem") || "").trim();
  const payload = {
    subject: (extra && extra.subject) || fd.get("subject"),
    source: fd.get("source"),
    stem: stem || "看图",
    options,
    correctAnswer: (extra && extra.correctAnswer) || fd.get("correctAnswer"),
    userWrongAnswer: (extra && extra.userWrongAnswer) || fd.get("userWrongAnswer"),
    knowledge: (extra && extra.knowledge) || fd.get("knowledge"),
    explanation: (extra && extra.explanation) || fd.get("explanation"),
    tags,
    imageData: extra && extra.imageData != null ? extra.imageData : imageData,
  };
  if (extra.updateExisting && lastSavedId) {
    payload.id = lastSavedId;
  }
  if (!payload.imageData && payload.stem === "看图") {
    throw new Error("请先拍照或选一张图片");
  }
  const res = await fetch(api("/items"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!data.ok) throw new Error(data.error || "保存失败");
  if (payload.imageData) {
    preview.src = payload.imageData;
    preview.hidden = false;
  }
  video.hidden = true;
  renderStats(data.stats);
  if (data.item && data.item.id) lastSavedId = data.item.id;
  setSubmitLabel(lastSavedId ? "更新本题" : "保存题目");
  return data;
}

function setSubmitLabel(text) {
  const btn = $("#form") && $("#form").querySelector("button[type=\"submit\"]");
  if (btn) btn.textContent = text;
}

function fillFormFromOcr(fields) {
  if (!fields) return;
  const set = (name, value) => {
    if (!value) return;
    const el = $(`[name="${name}"]`);
    if (el) el.value = value;
  };
  set("stem", fields.stem);
  set("subject", fields.subject);
  set("correctAnswer", fields.correctAnswer);
  set("userWrongAnswer", fields.userWrongAnswer);
  set("knowledge", fields.knowledge);
  set("explanation", flattenBrokenText(fields.explanation));
}

async function recognizePhoto(dataUrl) {
  return fetchJson("/api/ocr", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ imageData: dataUrl }),
  }, 60000);
}

async function solveFields(fields) {
  const res = await fetchJson("/api/solve", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stem: fields.stem || "", text: fields.text || fields.stem || "" }),
  }, 50000);
  if (res && res.ok && res.fields) {
    return Object.assign({}, fields, res.fields, { solved: true });
  }
  return Object.assign({}, fields, { solveError: (res && res.error) || "解析未生成" });
}

async function ingestPhotoFile(file, autoSave) {
  imageData = await compressFile(file);
  preview.src = imageData;
  preview.hidden = false;
  video.hidden = true;
  if (!autoSave) return 0;
  showSaveOk("正在识别题目（先出题，再生成解析）…");
  let extras = [{ imageData, stem: "看图" }];
  let afterMsg = "";
  try {
    const ocr = await recognizePhoto(imageData);
    const list = (ocr.items && ocr.items.length) ? ocr.items : (ocr.ok && ocr.fields ? [ocr.fields] : []);
    if (ocr.ok && list.length) {
      extras = list.map((fields) => ({
        imageData,
        stem: fields.stem || "看图",
        subject: fields.subject,
        correctAnswer: fields.correctAnswer,
        userWrongAnswer: fields.userWrongAnswer,
        knowledge: fields.knowledge,
        explanation: fields.explanation,
        text: fields.text,
      }));
      fillFormFromOcr(list[list.length - 1]);
      if (list[0].solveError) {
        afterMsg = "已入库。解析生成失败：" + list[0].solveError;
      } else if (extras.some((x) => x.explanation || x.correctAnswer)) {
        afterMsg = list.length > 1
          ? `这张图拆成 ${list.length} 道题并已入库。可在「题库」查看。`
          : "已入库，解析已生成。不是错题也可以。改文字请点「更新本题」。";
      } else {
        afterMsg = list.length > 1
          ? `这张图拆成 ${list.length} 道题并已入库。解析可稍后补。`
          : "已入库。解析未生成时，可在下方自己补，或开通腾讯混元后再拍。";
      }
    } else {
      afterMsg = (ocr && ocr.error) || "识别失败，已按图片入库。可稍后补文字。";
    }
  } catch (err) {
    afterMsg = (err && err.message) || "识别失败，请换一张图再试。";
  }
  let saved = 0;
  for (const extra of extras) {
    lastSavedId = "";
    const savedData = await saveItem(extra);
    saved += 1;
    const itemId = savedData && savedData.item && savedData.item.id;
    showSaveOk(`第 ${saved} 题已入库，正在生成解析…`);
    try {
      const solved = await solveFields(extra);
      if (itemId && (solved.explanation || solved.correctAnswer)) {
        lastSavedId = itemId;
        await saveItem(Object.assign({}, extra, solved, { updateExisting: true }));
        fillFormFromOcr(solved);
      } else if (solved.solveError) {
        afterMsg = afterMsg || solved.solveError;
      }
    } catch (err) {
      afterMsg = afterMsg || ((err && err.message) || "解析超时，题目已保存");
    }
  }
  showSaveOk(afterMsg || `已入库 ${saved} 道题。`);
  return saved;
}

async function ingestPhotoFiles(fileList) {
  const files = [...fileList].filter(Boolean);
  if (!files.length) return;
  if (ingestBusy) {
    showSaveOk("上一张还在处理，请稍等再选图。");
    return;
  }
  ingestBusy = true;
  try {
    let total = 0;
    for (let i = 0; i < files.length; i += 1) {
      showSaveOk(`正在处理第 ${i + 1}/${files.length} 张照片…`);
      total += await ingestPhotoFile(files[i], true) || 0;
    }
    if (files.length > 1) {
      showSaveOk(`已处理 ${files.length} 张照片，共入库 ${total} 道题。`);
    }
  } finally {
    ingestBusy = false;
  }
}

async function startCamera() {
  if (stream) return;
  stream = await navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" } },
    audio: false,
  });
  video.srcObject = stream;
  video.hidden = false;
  preview.hidden = true;
}

if (!window.isSecureContext) {
  $$(".live-cam").forEach((el) => {
    el.hidden = true;
  });
}

$("#btnPhotoIn").addEventListener("click", () => {
  const mobile = /Mobile|Android|iPhone|iPad/i.test(navigator.userAgent);
  if (mobile) $("#file").click();
  else $("#fileAlbum").click();
});

$("#btnStart").addEventListener("click", () => {
  startCamera().catch(() => $("#file").click());
});

$("#btnSnap").addEventListener("click", async () => {
  try {
    if (!stream) await startCamera();
  } catch (e) {
    $("#file").click();
    return;
  }
  canvas.width = video.videoWidth || 1280;
  canvas.height = video.videoHeight || 720;
  canvas.getContext("2d").drawImage(video, 0, 0);
  imageData = canvas.toDataURL("image/jpeg", 0.86);
  preview.src = imageData;
  preview.hidden = false;
  video.hidden = true;
  lastSavedId = "";
  try {
    await saveItem({ imageData, stem: "看图" });
    showSaveOk("已拍照入库。改文字请点「更新本题」，不要再点成新增。");
  } catch (err) {
    alert(err.message);
  }
});

$("#file").addEventListener("change", async (ev) => {
  const files = ev.target.files;
  ev.target.value = "";
  if (!files || !files.length) return;
  try {
    await ingestPhotoFiles(files);
  } catch (err) {
    alert(err.message);
  }
});

$("#fileAlbum").addEventListener("change", async (ev) => {
  const files = ev.target.files;
  ev.target.value = "";
  if (!files || !files.length) return;
  try {
    await ingestPhotoFiles(files);
  } catch (err) {
    alert(err.message);
  }
});

$("#form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  try {
    await saveItem({ updateExisting: Boolean(lastSavedId) });
    ev.target.reset();
    lastSavedId = "";
    imageData = "";
    setSubmitLabel("放入错题库");
    showSaveOk("已保存到题库（同一题不会重复新增）。");
  } catch (err) {
    alert(err.message);
  }
});

$("#btnQuiz").addEventListener("click", async () => {
  const n = Number($("#practiceN").value || 8);
  const subject = $("#practiceSubject").value.trim();
  const res = await fetch(api("/quiz", { n: String(n), subject }));
  const data = await res.json();
  quizQueue = data.items || [];
  quizIndex = 0;
  revealed = false;
  if (!quizQueue.length) {
    quizEl.innerHTML = `<div class="card">题库是空的，先去拍照入库。</div>`;
    return;
  }
  renderQuiz();
});

function practiceStem(item) {
  let s = String((item && item.stem) || "");
  s = s.replace(/\$\$[\s\S]*?\$\$/g, " ");
  s = s.replace(/\$[^$\n]*\$/g, " ");
  s = s.split(/\sX\s|×|✘|→|->/)[0];
  s = s.split(/应为|正确答案|正确[:：]|因数拆错|配方公式|用错|故x=|故 x=/)[0];
  s = s.replace(/\s+/g, " ").trim();
  const numbered = s.match(/^(\d+\s*[.、．]\s*.{0,120}?=\s*0)/);
  if (numbered) s = numbered[1].trim();
  if (!s || s.length < 2) return "看图作答";
  return s;
}

function prettyMath(s) {
  return String(s || "").replace(/([a-zA-Z])(\d+)\b/g, (_, letter, digits) => {
    const sup = "⁰¹²³⁴⁵⁶⁷⁸⁹";
    return letter + [...digits].map((d) => sup[Number(d)] || d).join("");
  });
}

function answerParts(item) {
  const correct = flattenBrokenText(item.correctAnswer);
  const wrong = flattenBrokenText(item.userWrongAnswer);
  let expl = flattenBrokenText(item.explanation);
  const full = flattenBrokenText(item.stem);
  const q = practiceStem(item);
  if (!expl && full && q && full.length > q.length + 2) {
    const i = full.indexOf(q);
    expl = flattenBrokenText(i >= 0 ? full.slice(i + q.length) : full);
    expl = expl.replace(/^\s*X\s*/i, "").trim();
  }
  return { correct, wrong, expl };
}

function renderQuiz() {
  const it = quizQueue[quizIndex];
  if (!it) {
    quizEl.innerHTML = `<div class="card">本组练习结束。可以再开一轮。</div>`;
    loadBank();
    return;
  }
  const stem = prettyMath(practiceStem(it));
  const showPhoto = Boolean(it.imageFile) && (revealed || stem === "看图作答");
  const ans = answerParts(it);
  const answerHtml = revealed ? `
      <div id="answerBox" class="hidden-answer">
        ${ans.correct ? `<p><b>正确答案：</b>${escapeHtml(prettyMath(ans.correct))}</p>` : ""}
        ${ans.wrong ? `<p><b>当时错选：</b>${escapeHtml(prettyMath(ans.wrong))}</p>` : ""}
        ${ans.expl ? `<p class="explain"><b>解析：</b>${escapeHtml(prettyMath(ans.expl))}</p>` : ""}
        ${!ans.correct && !ans.wrong && !ans.expl ? `<p>这张原图里有批改，请对照图片。</p>` : ""}
      </div>` : "";
  quizEl.innerHTML = `
    <article class="card quiz-card">
      <p class="meta">${quizIndex + 1} / ${quizQueue.length} · ${escapeHtml(it.subject || "未分类")} · ${escapeHtml(it.knowledge || "")}</p>
      ${showPhoto ? `<img class="quiz-img" src="${imgUrl(it.imageFile)}" alt="题目图片" />` : ""}
      <h2>${escapeHtml(stem)}</h2>
      <p class="hint">${revealed ? "对照答案后，点「做对了」或「还是错」。" : "先自己做，再点「看答案」。原图有批改，揭晓前不显示，以免看到答案。"}</p>
      ${answerHtml}
      <div class="camera-actions">
        ${revealed ? "" : `<button type="button" class="ghost" id="btnReveal">看答案</button>`}
        <button type="button" class="primary" id="btnRight">做对了</button>
        <button type="button" class="ghost" id="btnWrong">还是错</button>
      </div>
    </article>
  `;
  const revealBtn = $("#btnReveal");
  if (revealBtn) {
    revealBtn.addEventListener("click", () => {
      revealed = true;
      renderQuiz();
    });
  }
  $("#btnRight").addEventListener("click", () => submitReview("correct"));
  $("#btnWrong").addEventListener("click", () => submitReview("wrong"));
}

async function submitReview(result) {
  const it = quizQueue[quizIndex];
  await fetch(api(`/items/${it.id}/review`), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ result }),
  });
  quizIndex += 1;
  revealed = false;
  renderQuiz();
}

function flattenBrokenText(s) {
  const raw = String(s ?? "").replace(/\r\n/g, "\n").trim();
  if (!raw) return "";
  const lines = raw.split("\n").map((x) => x.trim()).filter(Boolean);
  if (!lines.length) return raw.replace(/\s+/g, " ").trim();
  const short = lines.filter((x) => x.length <= 2).length;
  const joined = lines.length >= 4 && short >= lines.length * 0.45
    ? lines.join("")
    : lines.join(" ");
  return joined.replace(/\s+/g, " ").trim();
}

function escapeHtml(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

ensureNotebook().then(() => loadBank()).catch((err) => {
  $("#shareLine").textContent = err.message || "无法打开错题本";
});
