let currentTrace = null;
let currentStep = null;
let activeTab = "output";

// ── Init ────────────────────────────
loadTraces();

// ── Trace list ──────────────────────
async function loadTraces() {
  const box = document.getElementById("traceList");
  try {
    const res = await fetch("/debug/traces");
    const traces = await res.json();
    if (!traces.length) {
      box.innerHTML = '<p class="hint">暂无 Trace 记录<br><br>请设置 DEBUG_TRACE=true<br>并运行一次完整分析</p>';
      return;
    }
    box.innerHTML = traces.map(t => `
      <div class="trace-item" onclick="loadTrace('${t.trace_id}')">
        <div class="tid">${t.trace_id.slice(-16)}</div>
        <div class="meta">${t.step_count} 步 · ${t.duration_seconds}s · ${t.status}</div>
      </div>
    `).join("");
  } catch (e) {
    box.innerHTML = '<p class="hint">加载失败: ' + e.message + '</p>';
  }
}

async function loadTrace(traceId) {
  try {
    const res = await fetch(`/debug/traces/${traceId}`);
    currentTrace = await res.json();
    currentStep = null;

    document.getElementById("traceMeta").innerHTML = `
      <span><strong>Trace ID:</strong> ${currentTrace.trace_id}</span>
      <span><strong>状态:</strong> ${currentTrace.status}</span>
      <span><strong>步骤:</strong> ${currentTrace.step_count}</span>
      <span><strong>耗时:</strong> ${currentTrace.duration_seconds}s</span>
    `;

    // Highlight active trace
    document.querySelectorAll(".trace-item").forEach(el => el.classList.remove("sel"));
    event?.target?.closest(".trace-item")?.classList.add("sel");

    renderSteps();
  } catch (e) {
    alert("加载 Trace 失败: " + e.message);
  }
}

// ── Step list ───────────────────────
function renderSteps() {
  const box = document.getElementById("stepList");
  const steps = currentTrace.steps || [];
  if (!steps.length) { box.innerHTML = '<p class="hint">无步骤数据</p>'; return; }

  box.innerHTML = steps.map((s, i) => {
    const cls = currentStep && currentStep.index === s.index ? "step-item sel" : "step-item";
    const errIcon = s.error ? '<span class="err">⚠</span>' : "";
    return `
      <div class="${cls}" onclick="selectStep(${i})">
        <span class="idx">${s.index}</span>${s.step_name}${errIcon}
      </div>`;
  }).join("");
}

function selectStep(idx) {
  currentStep = currentTrace.steps[idx];
  document.getElementById("stepTitle").innerText =
    `${currentStep.index}. ${currentStep.step_name}` +
    (currentStep.elapsed_ms ? `  (${(currentStep.elapsed_ms/1000).toFixed(1)}s)` : "");

  // Highlight active step
  document.querySelectorAll(".step-item").forEach(el => el.classList.remove("sel"));
  const items = document.querySelectorAll(".step-item");
  if (items[idx]) items[idx].classList.add("sel");

  showTab(activeTab);
}

// ── Tab switching ───────────────────
function showTab(field) {
  activeTab = field;
  if (!currentStep) {
    document.getElementById("jsonViewer").textContent = "— 请先选择步骤 —";
    return;
  }
  const value = currentStep[field];

  // Highlight active tab
  document.querySelectorAll(".tabs button").forEach(b => b.classList.remove("actv"));
  const btn = document.querySelector(`.tabs button[onclick="showTab('${field}')"]`);
  if (btn) btn.classList.add("actv");

  if (value === undefined || value === null) {
    document.getElementById("jsonViewer").textContent = "— (无数据) —";
    return;
  }
  if (typeof value === "string") {
    document.getElementById("jsonViewer").textContent = value;
    return;
  }
  if (Array.isArray(value) && value.every(v => typeof v === "string")) {
    document.getElementById("jsonViewer").textContent = value.join("\n");
    return;
  }
  document.getElementById("jsonViewer").textContent = JSON.stringify(value, null, 2);
}
