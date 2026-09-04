const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => [...document.querySelectorAll(sel)];

let notebookId = "";
let imageData = "";
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
        <p class="stem">${escapeHtml(it.stem || "（无题干）")}</p>
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

$("#btnStart").addEventListener("click", () => {
  startCamera().catch(() => alert("无法打开摄像头，请改用上传照片。"));
});

$("#btnSnap").addEventListener("click", async () => {
  try {
    if (!stream) await startCamera();
  } catch (e) {
    alert("无法打开摄像头，请改用上传照片。");
    return;
  }
  canvas.width = video.videoWidth || 1280;
  canvas.height = video.videoHeight || 720;
  canvas.getContext("2d").drawImage(video, 0, 0);
  imageData = canvas.toDataURL("image/jpeg", 0.86);
  preview.src = imageData;
  preview.hidden = false;
  video.hidden = true;
});

$("#file").addEventListener("change", (ev) => {
  const file = ev.target.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    imageData = String(reader.result);
    preview.src = imageData;
    preview.hidden = false;
    video.hidden = true;
  };
  reader.readAsDataURL(file);
});

$("#form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const options = String(fd.get("options") || "")
    .split("\n")
    .map((x) => x.trim())
    .filter(Boolean);
  const tags = String(fd.get("tags") || "")
    .split(/[,，]/)
    .map((x) => x.trim())
    .filter(Boolean);
  const payload = {
    subject: fd.get("subject"),
    source: fd.get("source"),
    stem: fd.get("stem"),
    options,
    correctAnswer: fd.get("correctAnswer"),
    userWrongAnswer: fd.get("userWrongAnswer"),
    knowledge: fd.get("knowledge"),
    explanation: fd.get("explanation"),
    tags,
    imageData,
  };
  const res = await fetch(api("/items"), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!data.ok) {
    alert(data.error || "保存失败");
    return;
  }
  ev.target.reset();
  imageData = "";
  preview.hidden = true;
  video.hidden = false;
  renderStats(data.stats);
  const ok = ev.target.querySelector(".save-ok");
  ok.hidden = false;
  ok.textContent = "已放入错题库，可到「题库」查看或「练习」开始。";
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

function renderQuiz() {
  const it = quizQueue[quizIndex];
  if (!it) {
    quizEl.innerHTML = `<div class="card">本组练习结束。可以再开一轮。</div>`;
    loadBank();
    return;
  }
  quizEl.innerHTML = `
    <article class="card quiz-card">
      <p class="meta">${quizIndex + 1} / ${quizQueue.length} · ${escapeHtml(it.subject || "未分类")} · ${escapeHtml(it.knowledge || "")}</p>
      ${it.imageFile ? `<img class="quiz-img" src="${imgUrl(it.imageFile)}" alt="题目图片" />` : ""}
      <h2>${escapeHtml(it.stem || "看图作答")}</h2>
      ${(it.options || []).map((o) => `<p>${escapeHtml(o)}</p>`).join("")}
      <p class="hint">先自己做，再揭晓。</p>
      <div id="answerBox" class="hidden-answer" ${revealed ? "" : "hidden"}>
        <p><b>正确答案：</b>${escapeHtml(it.correctAnswer || "（未填写）")}</p>
        <p><b>当时错选：</b>${escapeHtml(it.userWrongAnswer || "（未填写）")}</p>
        <p><b>解析：</b>${escapeHtml(it.explanation || "（未填写）")}</p>
      </div>
      <div class="camera-actions">
        <button type="button" class="ghost" id="btnReveal">看答案</button>
        <button type="button" class="primary" id="btnRight">做对了</button>
        <button type="button" class="ghost" id="btnWrong">还是错</button>
      </div>
    </article>
  `;
  $("#btnReveal").addEventListener("click", () => {
    revealed = true;
    $("#answerBox").hidden = false;
  });
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
