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

/* ── Cảnh báo SMS (cần quyền quản trị: mạng LAN hoặc ADMIN_TOKEN) ── */
function smsHeaders() {
  const h = { 'Content-Type': 'application/json' };
  const t = sessionStorage.getItem('adminToken');
  if (t) h['X-Admin-Token'] = t;
  return h;
}

async function smsRequest(url, method, body) {
  const go = () => fetch(url, { method, headers: smsHeaders(), cache: 'no-store', body: body ? JSON.stringify(body) : undefined });
  let res = await go();
  if (res.status === 403) {
    const t = prompt('Cần mã quản trị (ADMIN_TOKEN) để đổi cài đặt SMS:');
    if (!t) return null;
    sessionStorage.setItem('adminToken', t);
    res = await go();
  }
  return res;
}

function smsMsg(text, bad) {
  const m = document.getElementById('smsMsg');
  m.textContent = text; m.style.color = bad ? 'var(--red, #d32f2f)' : 'var(--text2)';
}

async function loadSms() {
  const st = document.getElementById('smsStatus');
  try {
    const res = await smsRequest('/api/settings/sms', 'GET');
    if (!res) { st.textContent = 'Cần quyền quản trị để xem cài đặt SMS.'; return; }
    const s = await res.json();
    if (!res.ok) { st.textContent = s.error || 'Không có quyền.'; return; }
    document.getElementById('smsEnabled').checked = s.enabled;
    document.getElementById('smsPhones').value = s.phones.join(', ');
    document.getElementById('smsMinConf').value = s.min_conf;
    document.getElementById('smsCooldown').value = s.cooldown_min;
    document.getElementById('smsDaily').value = s.daily_max;
    document.getElementById('smsUpload').checked = s.include_upload;
    const l = s.last || {};
    st.textContent = (s.enabled ? 'Đang BẬT. ' : 'Đang tắt. ') +
      (l.ts ? `Lần gửi gần nhất ${new Date(l.ts * 1000).toLocaleString('vi-VN')}: ${l.ok ? 'thành công' : 'THẤT BẠI'} — ${l.detail}` : 'Chưa gửi tin nào.');
  } catch (e) { st.textContent = 'Không tải được cài đặt SMS.'; }
}

async function saveSms() {
  const body = {
    enabled: document.getElementById('smsEnabled').checked,
    phones: document.getElementById('smsPhones').value,
    min_conf: document.getElementById('smsMinConf').value,
    cooldown_min: document.getElementById('smsCooldown').value,
    daily_max: document.getElementById('smsDaily').value,
    include_upload: document.getElementById('smsUpload').checked,
  };
  const res = await smsRequest('/api/settings/sms', 'POST', body);
  if (!res) return false;
  const out = await res.json();
  if (!res.ok) { smsMsg(out.error || 'Lỗi lưu cài đặt.', true); return false; }
  smsMsg('Đã lưu cài đặt SMS.');
  loadSms();
  return true;
}

async function testSms() {
  if (!(await saveSms())) return;
  smsMsg('Đang gửi tin thử (có thể mất tới ~40 giây)...');
  const res = await smsRequest('/api/sms/test', 'POST');
  if (!res) return;
  const out = await res.json().catch(() => ({}));
  smsMsg(out.ok ? 'Đã gửi tin thử: ' + out.detail : 'Gửi thất bại: ' + (out.detail || out.error || 'lỗi không rõ'), !out.ok);
  loadSms();
}

function loadPage(page) {
  if (page === 'alerts') loadAlerts();
  else if (page === 'history') loadHistory();
  else if (page === 'device') loadDevice();
  else if (page === 'settings') { loadSettings(); loadSms(); }
  else if (page === 'overview' || page === 'ai') loadStats();
}

document.addEventListener('DOMContentLoaded', function () {
  const b = document.getElementById('settingsKeyBtn');
  if (b) b.addEventListener('click', () => {
    const k = document.getElementById('keyBtn');
    if (k) k.click();
    setTimeout(loadSettings, 1500);
  });
  const sv = document.getElementById('smsSave'), ts = document.getElementById('smsTest');
  if (sv) sv.addEventListener('click', saveSms);
  if (ts) ts.addEventListener('click', testSms);
  // làm mới trang đang mở mỗi 10 giây
  setInterval(() => {
    const p = document.getElementById('mainContent').dataset.page;
    if (['alerts', 'history', 'device'].includes(p)) loadPage(p);
  }, 10000);
});
