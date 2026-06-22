"use strict";

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => Array.from(document.querySelectorAll(sel));

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.status === 204 ? null : res.json();
}

function pctBar(pct) {
  const p = pct == null ? 0 : pct;
  const color = p >= 90 ? "var(--error)" : p >= 75 ? "var(--warn)" : "var(--accent)";
  return `<span class="usage-bar"><span class="track">
    <span class="fill" style="width:${p}%;background:${color}"></span></span>
    <span class="pct">${pct == null ? "—" : p + "%"}</span></span>`;
}

function card(label, value, unit, cls) {
  return `<div class="card ${cls || ""}">
    <div class="label">${label}</div>
    <div class="value">${value}<span class="unit">${unit || ""}</span></div>
  </div>`;
}

// ---------------------------------------------------------------- 버전

async function loadVersion() {
  try {
    const v = await api("/api/version");
    $("#version-badge").textContent = "v" + v.version;
    $("#footer-version").textContent = "v" + v.version;
    document.title = `san_sw v${v.version} — Brocade SAN Switch Manager`;
  } catch (e) {
    $("#version-badge").textContent = "v?";
  }
}

async function checkUpdate() {
  const badge = $("#update-badge");
  badge.classList.remove("hidden");
  badge.textContent = "확인 중…";
  try {
    const r = await api("/api/upgrade/check");
    if (r.error) {
      badge.textContent = "업데이트 확인 불가: " + r.error;
    } else if (r.update_available) {
      badge.innerHTML = `새 버전 ${r.latest} 있음 ` +
        (r.html_url ? `<a href="${r.html_url}" target="_blank">릴리스</a>` : "");
    } else {
      badge.textContent = `최신 버전(${r.current})`;
      setTimeout(() => badge.classList.add("hidden"), 4000);
    }
  } catch (e) {
    badge.textContent = "업데이트 확인 실패: " + e.message;
  }
}

// ---------------------------------------------------------------- 요약

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

  const tbody = $("#dc-table tbody");
  tbody.innerHTML = s.datacenters.map((d) => {
    const m = d.summary;
    return `<tr>
      <td>${d.region}</td><td>${d.dc}</td><td>${d.switch_count}</td>
      <td>${m.total_ports}</td>
      <td style="color:var(--used)">${m.used_ports}</td>
      <td style="color:var(--free)">${m.free_ports}</td>
      <td style="color:var(--error)">${m.error_ports}</td>
      <td>${pctBar(m.occupancy_pct)}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="8" class="muted">데이터센터 없음</td></tr>`;
}

// ---------------------------------------------------------------- 스위치 목록

async function loadSwitches() {
  const list = await api("/api/switches");
  const tbody = $("#switch-table tbody");
  tbody.innerHTML = list.map((sw) => {
    const m = sw.summary;
    return `<tr>
      <td class="clickable" data-id="${sw.id}">${sw.name || "(이름없음)"}</td>
      <td>${sw.ip}</td>
      <td>${sw.region} / ${sw.dc}</td>
      <td>${sw.model || "—"}</td>
      <td>${sw.fos_version || "—"}</td>
      <td><span class="status ${sw.status}">${statusLabel(sw.status)}</span></td>
      <td>${m.used_ports} / ${m.total_ports}</td>
      <td>${pctBar(m.occupancy_pct)}</td>
      <td><button class="btn btn-sm" data-poll="${sw.id}">폴링</button></td>
      <td><button class="btn btn-sm btn-ghost" data-del="${sw.id}">삭제</button></td>
    </tr>`;
  }).join("") || `<tr><td colspan="10" class="muted">스위치 없음 — 추가하세요</td></tr>`;

  $$("#switch-table td.clickable").forEach((el) =>
    el.addEventListener("click", () => openDetail(el.dataset.id)));
  $$("#switch-table [data-poll]").forEach((el) =>
    el.addEventListener("click", () => pollOne(el.dataset.poll)));
  $$("#switch-table [data-del]").forEach((el) =>
    el.addEventListener("click", () => delSwitch(el.dataset.del)));
}

function statusLabel(s) {
  return { online: "온라인", unreachable: "도달불가", unknown: "미확인" }[s] || s;
}

async function pollOne(id) {
  await api(`/api/switches/${id}/poll`, { method: "POST" });
  await refresh();
}

async function delSwitch(id) {
  if (!confirm("이 스위치를 삭제할까요?")) return;
  await api(`/api/switches/${id}`, { method: "DELETE" });
  await refresh();
}

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

  $("#port-grid").innerHTML = (sw.ports || []).map((p) => {
    const cls = p.operational_status === "online" || p.operational_status === "in_sync"
      ? "used"
      : ["laser_flt","port_flt","hard_flt","diag_flt","faulty","mod_inv"]
          .includes(p.operational_status) ? "error" : "";
    const speed = p.speed_gbps ? p.speed_gbps + "G" : "—";
    return `<div class="port ${cls}" title="${p.name} · ${p.operational_status}${
        p.neighbor_wwn ? " · " + p.neighbor_wwn : ""}">
      <div class="pname">${p.name}</div>
      <div class="pspeed">${speed}</div>
      <div class="ptype">${p.port_type || ""}</div>
    </div>`;
  }).join("") || `<div class="muted">포트 데이터 없음 — 폴링 필요</div>`;

  $("#detail-modal").classList.remove("hidden");
}

// ---------------------------------------------------------------- 추가/폴링

function openAdd() { $("#add-modal").classList.remove("hidden"); }
function closeAdd() { $("#add-modal").classList.add("hidden"); $("#add-form").reset(); }

async function submitAdd(e) {
  e.preventDefault();
  const f = e.target;
  const payload = {
    ip: f.ip.value.trim(),
    name: f.name.value.trim() || null,
    region: f.region.value.trim() || "global",
    dc: f.dc.value.trim() || "default",
    method: f.method.value,
    username: f.username.value.trim() || null,
    password: f.password.value || null,
    verify_tls: f.verify_tls.checked,
  };
  try {
    await api("/api/switches", { method: "POST", body: JSON.stringify(payload) });
    closeAdd();
    await refresh();
  } catch (err) {
    alert("추가 실패: " + err.message);
  }
}

async function pollAll() {
  const btn = $("#btn-poll");
  btn.disabled = true; btn.textContent = "폴링 중…";
  try { await api("/api/poll", { method: "POST" }); await refresh(); }
  finally { btn.disabled = false; btn.textContent = "전체 폴링"; }
}

// ---------------------------------------------------------------- 부트

async function refresh() {
  await Promise.all([loadSummary(), loadSwitches()]);
}

function wire() {
  $("#btn-poll").addEventListener("click", pollAll);
  $("#btn-check-update").addEventListener("click", checkUpdate);
  $("#btn-add").addEventListener("click", openAdd);
  $("#add-cancel").addEventListener("click", closeAdd);
  $("#add-form").addEventListener("submit", submitAdd);
  $("#detail-close").addEventListener("click", () =>
    $("#detail-modal").classList.add("hidden"));
  [$("#add-modal"), $("#detail-modal")].forEach((mod) =>
    mod.addEventListener("click", (e) => { if (e.target === mod) mod.classList.add("hidden"); }));
}

(async function init() {
  wire();
  await loadVersion();
  await refresh();
  // 30초마다 자동 새로고침
  setInterval(refresh, 30000);
})();
