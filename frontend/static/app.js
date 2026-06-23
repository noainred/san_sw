"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const TOKEN_KEY = "sansw_token";

async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  const tok = localStorage.getItem(TOKEN_KEY);
  if (tok) headers["Authorization"] = "Bearer " + tok;
  const res = await fetch(path, { ...opts, headers });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

const SVG_NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}, parent = null) => {
  const e = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v);
  if (parent) parent.appendChild(e);
  return e;
};

function card(label, value, unit, cls) {
  return `<div class="card ${cls || ""}"><div class="label">${label}</div>
    <div class="value">${value}<span class="unit">${unit || ""}</span></div></div>`;
}

function pctBar(pct) {
  const p = pct == null ? 0 : pct;
  const color = p >= 90 ? "var(--error)" : p >= 75 ? "var(--warn)" : "var(--accent)";
  return `<span class="usage-bar"><span class="track">
    <span class="fill" style="width:${p}%;background:${color}"></span></span>
    <span class="pct">${pct == null ? "—" : p + "%"}</span></span>`;
}

function drawLineChart(svg, emptyEl, values) {
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const vb = svg.viewBox.baseVal, W = vb.width, H = vb.height;
  const pad = { l: 34, r: 8, t: 10, b: 18 };
  const ok = values && values.length >= 2;
  if (emptyEl) emptyEl.style.display = ok ? "none" : "block";
  svg.style.display = ok ? "block" : "none";
  if (!ok) return;
  const iW = W - pad.l - pad.r, iH = H - pad.t - pad.b, n = values.length;
  const xAt = (i) => pad.l + (n === 1 ? iW / 2 : (i / (n - 1)) * iW);
  const yAt = (v) => pad.t + iH - (Math.max(0, Math.min(100, v)) / 100) * iH;
  [0, 50, 100].forEach((g) => {
    svgEl("line", { x1: pad.l, x2: W - pad.r, y1: yAt(g), y2: yAt(g),
      stroke: "#2d3845", "stroke-width": 1 }, svg);
    const t = svgEl("text", { x: 4, y: yAt(g) + 3, fill: "#8b98a5",
      "font-size": 10 }, svg);
    t.textContent = g + "%";
  });
  const pts = values.map((d, i) => `${xAt(i)},${yAt(d.y)}`).join(" ");
  svgEl("polygon", { points: `${pad.l},${yAt(0)} ${pts} ${xAt(n - 1)},${yAt(0)}`,
    fill: "rgba(79,156,249,0.12)" }, svg);
  svgEl("polyline", { points: pts, fill: "none", stroke: "#4f9cf9",
    "stroke-width": 2 }, svg);
  const last = values[n - 1];
  svgEl("circle", { cx: xAt(n - 1), cy: yAt(last.y), r: 3, fill: "#4f9cf9" }, svg);
}

const statusLabel = (s) =>
  ({ online: "온라인", unreachable: "도달불가", unknown: "미확인" }[s] || s);

// ---------------------------------------------------------------- 버전/인증

async function loadVersion() {
  try {
    const v = await api("/api/version");
    $("#version-badge").textContent = "v" + v.version;
    $("#footer-version").textContent = "v" + v.version;
    document.title = `san_sw v${v.version} — Brocade SAN Switch Manager`;
  } catch (e) { $("#version-badge").textContent = "v?"; }
}

async function initAuth() {
  try {
    const cfg = await api("/api/auth/config");
    if (cfg.auth_enabled) $("#btn-login").classList.remove("hidden");
    const me = await api("/api/auth/me").catch(() => null);
    if (me) $("#user-badge").textContent = `${me.username} (${me.role})`;
  } catch (e) {}
}

async function checkUpdate() {
  const b = $("#update-badge"); b.classList.remove("hidden"); b.textContent = "확인 중…";
  try {
    const r = await api("/api/upgrade/check");
    if (r.error) b.textContent = "업데이트 확인 불가: " + r.error;
    else if (r.update_available)
      b.innerHTML = `새 버전 ${r.latest} 있음 ` +
        (r.html_url ? `<a href="${r.html_url}" target="_blank">릴리스</a>` : "");
    else { b.textContent = `최신 버전(${r.current})`;
      setTimeout(() => b.classList.add("hidden"), 4000); }
  } catch (e) { b.textContent = "업데이트 확인 실패: " + e.message; }
}

// ---------------------------------------------------------------- 대시보드

async function loadSummary() {
  const s = await api("/api/summary");
  const g = s.global;
  $("#global-cards").innerHTML = [
    card("스위치", s.switch_count, "대", "accent"),
    card("전체 포트", g.total_ports, "개"),
    card("사용중", g.used_ports, "개", "used"),
    card("비어있음", g.free_ports, "개", "free"),
    card("장애", g.error_ports, "개", "error"),
    card("포트 사용율", g.occupancy_pct, "%", "accent"),
  ].join("");
  await loadGlobalHistory();
  $("#dc-table tbody").innerHTML = s.datacenters.map((d) => {
    const m = d.summary;
    return `<tr><td>${d.region}</td><td>${d.dc}</td><td>${d.switch_count}</td>
      <td>${m.total_ports}</td><td style="color:var(--used)">${m.used_ports}</td>
      <td style="color:var(--free)">${m.free_ports}</td>
      <td style="color:var(--error)">${m.error_ports}</td>
      <td>${pctBar(m.occupancy_pct)}</td></tr>`;
  }).join("") || `<tr><td colspan="8" class="muted">데이터센터 없음</td></tr>`;
}

async function loadGlobalHistory() {
  try {
    const r = await api("/api/summary/history?limit=120");
    const pts = (r.history || []).map((h) => ({ x: h.ts, y: h.occupancy_pct }));
    drawLineChart($("#global-chart"), $("#global-chart-empty"), pts);
    const range = $("#global-chart-range");
    range.textContent = pts.length >= 2
      ? `${pts[0].x} ~ ${pts[pts.length - 1].x} (${pts.length}p)` : "";
  } catch (e) { drawLineChart($("#global-chart"), $("#global-chart-empty"), []); }
}

async function loadSwitches() {
  const list = await api("/api/switches");
  $("#switch-table tbody").innerHTML = list.map((sw) => {
    const m = sw.summary;
    return `<tr>
      <td class="clickable" data-id="${sw.id}">${sw.name || "(이름없음)"}</td>
      <td>${sw.ip}</td><td>${sw.region} / ${sw.dc}</td><td>${sw.model || "—"}</td>
      <td>${sw.fos_version || "—"}</td>
      <td><span class="status ${sw.status}">${statusLabel(sw.status)}</span></td>
      <td>${m.used_ports} / ${m.total_ports}</td><td>${pctBar(m.occupancy_pct)}</td>
      <td><button class="btn btn-sm" data-poll="${sw.id}">폴링</button></td>
      <td><button class="btn btn-sm btn-ghost" data-del="${sw.id}">삭제</button></td>
    </tr>`;
  }).join("") || `<tr><td colspan="10" class="muted">스위치 없음 — 추가하세요</td></tr>`;
  $$("#switch-table td.clickable").forEach((el) =>
    el.addEventListener("click", () => openDetail(el.dataset.id)));
  $$("#switch-table [data-poll]").forEach((el) =>
    el.addEventListener("click", () => act(() => api(`/api/switches/${el.dataset.poll}/poll`, { method: "POST" }))));
  $$("#switch-table [data-del]").forEach((el) =>
    el.addEventListener("click", () => {
      if (confirm("이 스위치를 삭제할까요?"))
        act(() => api(`/api/switches/${el.dataset.del}`, { method: "DELETE" }));
    }));
}

async function act(fn) { try { await fn(); await refreshActive(); }
  catch (e) { alert("실패: " + e.message); } }

// ---------------------------------------------------------------- 상세

async function openDetail(id) {
  const sw = await api(`/api/switches/${id}`);
  $("#detail-title").textContent =
    `${sw.name || sw.ip} — ${sw.region}/${sw.dc} (${sw.model || "모델미상"})`;
  const m = sw.summary;
  $("#detail-summary").innerHTML = [
    card("전체 포트", m.total_ports, "개"),
    card("사용중", m.used_ports, "개", "used"),
    card("비어있음", m.free_ports, "개", "free"),
    card("장애", m.error_ports, "개", "error"),
    card("포트 사용율", m.occupancy_pct, "%", "accent"),
    card("평균 대역폭", m.avg_util_pct == null ? "—" : m.avg_util_pct,
      m.avg_util_pct == null ? "" : "%"),
  ].join("");
  try {
    const sres = await api(`/api/switches/${id}/samples?limit=120`);
    drawLineChart($("#detail-chart"), $("#detail-chart-empty"),
      (sres.samples || []).map((s) => ({ x: s.ts, y: s.occupancy_pct })));
  } catch (e) { drawLineChart($("#detail-chart"), $("#detail-chart-empty"), []); }

  $("#port-grid").innerHTML = (sw.ports || []).map((p) => {
    const online = ["online", "in_sync"].includes(p.operational_status);
    const isErr = ["laser_flt","port_flt","hard_flt","diag_flt","faulty","mod_inv"]
      .includes(p.operational_status);
    const warn = online && ((p.crc_errors || 0) > 1000 ||
      (p.sfp_rx_power_dbm != null && p.sfp_rx_power_dbm < -15));
    const cls = isErr ? "error" : warn ? "warn" : online ? "used" : "";
    const tip = [`${p.name} · ${p.operational_status}`,
      p.speed_gbps ? p.speed_gbps + "G" : null,
      p.crc_errors != null ? `CRC ${p.crc_errors}` : null,
      p.sfp_rx_power_dbm != null ? `Rx ${p.sfp_rx_power_dbm}dBm` : null,
      p.sfp_temp_c != null ? `${p.sfp_temp_c}℃` : null,
      p.neighbor_wwn || null].filter(Boolean).join(" · ");
    return `<div class="port ${cls}" title="${tip}">
      <div class="pname">${p.name}</div>
      <div class="pspeed">${p.speed_gbps ? p.speed_gbps + "G" : "—"}</div>
      <div class="ptype">${p.port_type || ""}</div></div>`;
  }).join("") || `<div class="muted">포트 데이터 없음 — 폴링 필요</div>`;
  $("#detail-modal").classList.remove("hidden");
}

// ---------------------------------------------------------------- 지도

async function loadMap() {
  const svg = $("#world-map");
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const W = 1000, H = 500;
  svgEl("rect", { x: 0, y: 0, width: W, height: H, fill: "#0d1b2a",
    stroke: "#2d3845" }, svg);
  for (let lon = -180; lon <= 180; lon += 30)
    svgEl("line", { x1: (lon + 180) / 360 * W, y1: 0,
      x2: (lon + 180) / 360 * W, y2: H, stroke: "#16263a" }, svg);
  for (let lat = -90; lat <= 90; lat += 30)
    svgEl("line", { x1: 0, y1: (90 - lat) / 180 * H, x2: W,
      y2: (90 - lat) / 180 * H, stroke: "#16263a" }, svg);
  const list = await api("/api/switches");
  const geo = list.filter((s) => s.lat != null && s.lon != null);
  geo.forEach((s) => {
    const x = (s.lon + 180) / 360 * W, y = (90 - s.lat) / 180 * H;
    const r = Math.max(5, Math.sqrt(s.summary.total_ports) * 1.6);
    const color = s.status === "online" ? "#2ea043"
      : s.status === "unreachable" ? "#f85149" : "#6e7681";
    const c = svgEl("circle", { cx: x, cy: y, r, fill: color,
      "fill-opacity": 0.7, stroke: "#e6edf3", "stroke-width": 1 }, svg);
    c.style.cursor = "pointer";
    c.addEventListener("click", () => openDetail(s.id));
    const t = svgEl("text", { x: x + r + 3, y: y + 4, fill: "#e6edf3",
      "font-size": 12 }, svg);
    t.textContent = `${s.name || s.ip} (${s.summary.occupancy_pct}%)`;
  });
  if (!geo.length) {
    const t = svgEl("text", { x: W / 2, y: H / 2, fill: "#8b98a5",
      "font-size": 16, "text-anchor": "middle" }, svg);
    t.textContent = "지오좌표(lat/lon)가 설정된 스위치가 없습니다";
  }
}

// ---------------------------------------------------------------- 토폴로지

async function loadTopology() {
  const svg = $("#topo-svg");
  while (svg.firstChild) svg.removeChild(svg.firstChild);
  const g = await api("/api/topology");
  const W = 800, H = 500, cx = W / 2, cy = H / 2, R = 180;
  const n = g.nodes.length;
  const pos = {};
  g.nodes.forEach((nd, i) => {
    const a = (i / Math.max(1, n)) * Math.PI * 2 - Math.PI / 2;
    pos[nd.id] = { x: cx + R * Math.cos(a), y: cy + R * Math.sin(a) };
  });
  g.edges.forEach((e) => {
    const a = pos[e.source], b = pos[e.target];
    if (a && b) svgEl("line", { x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      stroke: "#4f9cf9", "stroke-width": 2, "stroke-opacity": 0.6 }, svg);
  });
  g.nodes.forEach((nd) => {
    const p = pos[nd.id];
    const color = nd.status === "online" ? "#2ea043"
      : nd.status === "unreachable" ? "#f85149" : "#6e7681";
    const c = svgEl("circle", { cx: p.x, cy: p.y, r: 16, fill: color,
      stroke: "#e6edf3", "stroke-width": 1.5 }, svg);
    c.style.cursor = "pointer";
    c.addEventListener("click", () => openDetail(nd.id));
    const t = svgEl("text", { x: p.x, y: p.y + 30, fill: "#e6edf3",
      "font-size": 12, "text-anchor": "middle" }, svg);
    t.textContent = nd.name;
  });
  if (!n) {
    const t = svgEl("text", { x: cx, y: cy, fill: "#8b98a5", "font-size": 16,
      "text-anchor": "middle" }, svg);
    t.textContent = "토폴로지 데이터 없음";
  }
}

// ---------------------------------------------------------------- 펌웨어

async function loadFirmware() {
  const f = await api("/api/firmware");
  const sc = f.status_counts || {};
  $("#fw-cards").innerHTML = [
    card("지원중", sc.supported || 0, "대", "used"),
    card("EoL 임박", sc.eol_soon || 0, "대", "warn"),
    card("EoL 경과", sc.eol || 0, "대", "error"),
    card("미상", sc.unknown || 0, "대", "free"),
  ].join("");
  $("#fw-note").textContent = f.note || "";
  const lbl = { supported: "지원중", eol_soon: "EoL 임박", eol: "EoL 경과",
    unknown: "미상" };
  $("#fw-table tbody").innerHTML = (f.switches || []).map((s) =>
    `<tr><td>${s.name || s.switch_id}</td><td>${s.region}/${s.dc}</td>
     <td>${s.version || "—"}</td><td>${s.eol || "—"}</td>
     <td>${s.days_left == null ? "—" : s.days_left}</td>
     <td><span class="status ${s.status === "supported" ? "online"
       : s.status === "eol" ? "unreachable" : "unknown"}">${lbl[s.status]}</span></td>
     </tr>`).join("") || `<tr><td colspan="6" class="muted">데이터 없음</td></tr>`;
}

// ---------------------------------------------------------------- 알림

async function loadAlerts() {
  const rules = (await api("/api/alert-rules")).rules;
  $("#rules-table tbody").innerHTML = rules.map((r) =>
    `<tr><td>${r.name}</td><td>${r.metric}</td>
     <td>${r.comparator} ${r.threshold}</td>
     <td><span class="status ${r.severity === "critical" ? "unreachable"
       : r.severity === "warning" ? "unknown" : "online"}">${r.severity}</span></td>
     <td>${r.enabled ? "✓" : "—"}</td>
     <td><button class="btn btn-sm btn-ghost" data-delrule="${r.id}">삭제</button></td>
     </tr>`).join("") || `<tr><td colspan="6" class="muted">규칙 없음</td></tr>`;
  $$("#rules-table [data-delrule]").forEach((el) =>
    el.addEventListener("click", () =>
      act(() => api(`/api/alert-rules/${el.dataset.delrule}`, { method: "DELETE" }))));
  const alerts = (await api("/api/alerts")).alerts;
  $("#alerts-table tbody").innerHTML = alerts.map((a) =>
    `<tr><td>${a.ts}</td>
     <td><span class="status ${a.severity === "critical" ? "unreachable"
       : "unknown"}">${a.severity}</span></td>
     <td>${a.message}</td><td>${a.value == null ? "—" : a.value}</td></tr>`)
    .join("") || `<tr><td colspan="4" class="muted">발생한 알림 없음</td></tr>`;
}

// ---------------------------------------------------------------- 리포트

async function loadReports() {
  const r = await api("/api/reports/capacity");
  const t = r.totals;
  $("#rep-cards").innerHTML = [
    card("전체 포트", t.total_ports, "개"),
    card("사용중", t.used_ports, "개", "used"),
    card("여유", t.free_ports, "개", "free"),
    card("사용율", t.occupancy_pct, "%", "accent"),
  ].join("");
  const tr = r.trend;
  const dirLbl = { rising: "상승", falling: "하락", stable: "유지",
    insufficient: "데이터 부족" };
  $("#rep-trend").textContent = `사용율 추세: ${dirLbl[tr.direction] || tr.direction}`
    + (tr.first_pct != null ? ` (${tr.first_pct}% → ${tr.last_pct}%)` : "");
  $("#rep-speed").innerHTML = Object.entries(r.speed_distribution || {})
    .map(([k, v]) => `<span class="chip">${k}: ${v}포트</span>`).join("")
    || `<span class="muted">데이터 없음</span>`;
  $("#rep-dc tbody").innerHTML = (r.datacenters || []).map((d) => {
    const m = d.summary;
    return `<tr><td>${d.region}</td><td>${d.dc}</td><td>${m.total_ports}</td>
      <td>${m.used_ports}</td><td>${m.free_ports}</td>
      <td>${pctBar(m.occupancy_pct)}</td></tr>`;
  }).join("") || `<tr><td colspan="6" class="muted">데이터 없음</td></tr>`;
}

// ---------------------------------------------------------------- 감사

async function loadAudit() {
  const a = (await api("/api/audit")).audit;
  $("#audit-table tbody").innerHTML = a.map((r) =>
    `<tr><td>${r.ts}</td><td>${r.username || "—"}</td><td>${r.action}</td>
     <td>${r.target || "—"}</td><td>${r.detail || "—"}</td></tr>`).join("")
    || `<tr><td colspan="5" class="muted">로그 없음</td></tr>`;
}

// ---------------------------------------------------------------- 탭/부트

const LOADERS = {
  dashboard: async () => { await Promise.all([loadSummary(), loadSwitches()]); },
  map: loadMap, topology: loadTopology, firmware: loadFirmware,
  alerts: loadAlerts, reports: loadReports, audit: loadAudit,
};
let activeTab = "dashboard";

async function showTab(name) {
  activeTab = name;
  $$(".tab").forEach((t) => t.classList.toggle("active", t.dataset.tab === name));
  $$(".tab-section").forEach((s) =>
    s.classList.toggle("active", s.id === "tab-" + name));
  try { await LOADERS[name](); } catch (e) { console.error(e); }
}
async function refreshActive() { try { await LOADERS[activeTab](); } catch (e) {} }

function modal(id, show) { $("#" + id).classList.toggle("hidden", !show); }

function wire() {
  $$(".tab").forEach((t) => t.addEventListener("click", () => showTab(t.dataset.tab)));
  $("#btn-poll").addEventListener("click", async () => {
    const b = $("#btn-poll"); b.disabled = true; b.textContent = "폴링 중…";
    try { await api("/api/poll", { method: "POST" }); await refreshActive(); }
    catch (e) { alert(e.message); }
    finally { b.disabled = false; b.textContent = "전체 폴링"; }
  });
  $("#btn-check-update").addEventListener("click", checkUpdate);
  $("#btn-add").addEventListener("click", () => modal("add-modal", true));
  $("#add-cancel").addEventListener("click", () => modal("add-modal", false));
  $("#add-form").addEventListener("submit", async (e) => {
    e.preventDefault(); const f = e.target;
    try {
      await api("/api/switches", { method: "POST", body: JSON.stringify({
        ip: f.ip.value.trim(), name: f.name.value.trim() || null,
        region: f.region.value.trim() || "global",
        dc: f.dc.value.trim() || "default", method: f.method.value,
        username: f.username.value.trim() || null,
        password: f.password.value || null, verify_tls: f.verify_tls.checked }) });
      modal("add-modal", false); f.reset(); await showTab("dashboard");
    } catch (err) { alert("추가 실패: " + err.message); }
  });
  $("#btn-add-rule").addEventListener("click", () => modal("rule-modal", true));
  $("#rule-cancel").addEventListener("click", () => modal("rule-modal", false));
  $("#rule-form").addEventListener("submit", async (e) => {
    e.preventDefault(); const f = e.target;
    try {
      await api("/api/alert-rules", { method: "POST", body: JSON.stringify({
        name: f.name.value, metric: f.metric.value, comparator: f.comparator.value,
        threshold: parseFloat(f.threshold.value), severity: f.severity.value }) });
      modal("rule-modal", false); f.reset(); await loadAlerts();
    } catch (err) { alert("규칙 추가 실패: " + err.message); }
  });
  $("#btn-eval").addEventListener("click", () =>
    act(() => api("/api/alerts/evaluate", { method: "POST" })));
  $("#btn-login").addEventListener("click", () => modal("login-modal", true));
  $("#login-cancel").addEventListener("click", () => modal("login-modal", false));
  $("#login-form").addEventListener("submit", async (e) => {
    e.preventDefault(); const f = e.target;
    try {
      const r = await api("/api/auth/login", { method: "POST",
        body: JSON.stringify({ username: f.username.value,
          password: f.password.value }) });
      localStorage.setItem(TOKEN_KEY, r.token);
      $("#user-badge").textContent = `${r.username} (${r.role})`;
      modal("login-modal", false); await refreshActive();
    } catch (err) { alert("로그인 실패: " + err.message); }
  });
  $("#detail-close").addEventListener("click", () => modal("detail-modal", false));
  ["add-modal", "detail-modal", "rule-modal", "login-modal"].forEach((id) =>
    $("#" + id).addEventListener("click", (e) => {
      if (e.target === $("#" + id)) modal(id, false);
    }));
}

(async function init() {
  wire();
  await loadVersion();
  await initAuth();
  await showTab("dashboard");
  setInterval(refreshActive, 30000);
})();
