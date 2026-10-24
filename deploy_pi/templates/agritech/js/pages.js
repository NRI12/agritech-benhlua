/* ── Dữ liệu cho các trang Cảnh báo / Lịch sử / Thiết bị / Cài đặt ── */

const SOURCE_VI = { camera: 'Camera', upload: 'Ảnh tải lên' };
const SEV_CLS = { 'Nặng': 'sev-high', 'Trung bình': 'sev-mid', 'Nhẹ': 'sev-low' };

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}
function fmtTime(ts) { return new Date(ts * 1000).toLocaleString('vi-VN'); }
function fmtUptime(s) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h} giờ ${m} phút` : `${m} phút`;
}

async function getJSON(url) { const r = await fetch(url, { cache: 'no-store' }); return r.json(); }

async function loadAlerts() {
  const box = document.getElementById('alertsList');
  try {
    const rows = await getJSON('/api/alerts');
    if (!rows.length) { box.className = 'list-empty'; box.textContent = 'Chưa có cảnh báo nào.'; return; }
    box.className = '';
    box.innerHTML = rows.map(r => `
      <div class="alert-row ${SEV_CLS[r.severity] || ''}">
        <i class="fas fa-triangle-exclamation"></i>
        <div><b>${esc(r.class_vi)}</b> — mức ${esc(r.severity)}, tin cậy ${esc(r.confidence)}%
          <div class="muted">${fmtTime(r.ts)} · ${SOURCE_VI[r.source] || esc(r.source)}</div></div>
      </div>`).join('');
  } catch (e) { box.textContent = 'Không tải được dữ liệu.'; }
}

async function loadHistory() {
  const body = document.getElementById('historyBody');
  try {
    const rows = await getJSON('/api/history?limit=200');
    body.innerHTML = rows.length ? rows.map(r => `
      <tr><td>${fmtTime(r.ts)}</td><td>${SOURCE_VI[r.source] || esc(r.source)}</td>
      <td>${esc(r.class_vi)}</td><td>${esc(r.confidence)}%</td>
      <td><span class="sev-pill ${SEV_CLS[r.severity] || ''}">${esc(r.severity)}</span></td></tr>`).join('')
      : '<tr><td colspan="5" class="list-empty">Chưa có lịch sử.</td></tr>';
  } catch (e) { body.innerHTML = '<tr><td colspan="5">Không tải được dữ liệu.</td></tr>'; }
}

function kv(rows) {
  return rows.map(([k, v]) => `<div class="kv-row"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('');
}

async function loadDevice() {
  const box = document.getElementById('deviceInfo');
  try {
    const d = await getJSON('/api/device');
    box.innerHTML = kv([
      ['Camera', d.camera_running ? `Đang chạy (${d.camera_source})` : 'Không kết nối'],
      ['Model', `${d.model_path} — ${d.classes} lớp ${d.model_loaded ? '(đã nạp)' : '(chưa nạp)'}`],
      ['Nhiệt độ CPU', d.cpu_temp != null ? d.cpu_temp + ' °C' : 'không đọc được'],
      ['RAM đang dùng', d.mem_used_pct != null ? d.mem_used_pct + ' %' : 'không đọc được'],
      ['Tải CPU (1 phút)', d.load1 ?? 'không đọc được'],
      ['Thời gian chạy', fmtUptime(d.uptime)],
      ['ChatGPT', d.chatgpt ? `Đã cấu hình (${d.chatgpt_model})` : 'Chưa có API key'],
    ]);
  } catch (e) { box.textContent = 'Không tải được dữ liệu.'; }
}

async function loadSettings() {
  try {
    const d = await getJSON('/api/device');
    document.getElementById('settingsKey').textContent = d.chatgpt
      ? `Đã cấu hình API key. Model: ${d.chatgpt_model}.` : 'Chưa có API key — chatbot đang dùng tư vấn có sẵn.';
    const t = d.thresholds;
    document.getElementById('settingsThr').innerHTML = kv([
      ['Ngưỡng "không chắc chắn"', t.conf * 100 + '%'],
      ['Lọc không phải lúa: màu thực vật tối thiểu', t.rice_min_vegetation * 100 + '%'],
      ['Lọc không phải lúa: entropy tối đa', t.rice_max_entropy],
      ['Lọc không phải lúa: độ tin cậy tối thiểu', t.rice_min_conf * 100 + '%'],
    ]);
  } catch (e) { /* bỏ qua */ }
}

function loadPage(page) {
  if (page === 'alerts') loadAlerts();
  else if (page === 'history') loadHistory();
  else if (page === 'device') loadDevice();
  else if (page === 'settings') loadSettings();
  else if (page === 'overview' || page === 'ai') loadStats();
}

document.addEventListener('DOMContentLoaded', function () {
  const b = document.getElementById('settingsKeyBtn');
  if (b) b.addEventListener('click', () => {
    const k = document.getElementById('keyBtn');
    if (k) k.click();
    setTimeout(loadSettings, 1500);
  });
  // làm mới trang đang mở mỗi 10 giây
  setInterval(() => {
    const p = document.getElementById('mainContent').dataset.page;
    if (['alerts', 'history', 'device'].includes(p)) loadPage(p);
  }, 10000);
});
