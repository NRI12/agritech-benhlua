/* ── Nối dashboard với backend Agritech ──────────────────────────────────
 * Camera chỉ để chụp ảnh; không suy luận liên tục. Kết quả đến từ:
 *   POST /api/capture        -> chụp 1 khung từ camera rồi phân tích
 *   POST /api/predict/image  -> phân tích ảnh người dùng chọn
 * Poll định kỳ chỉ còn: /api/sensors (cảm biến) và /api/health (trạng thái hệ thống).
 */

const DONUT_C = 238.8;            // chu vi vòng tròn r=38 (2*pi*38)
const SENSOR_MS = 5000;           // chu kỳ poll cảm biến
const HEALTH_MS = 10000;          // chu kỳ kiểm tra trạng thái hệ thống

function $(id) { return document.getElementById(id); }
function setText(id, txt) { const el = $(id); if (el) el.textContent = txt; }

/* ── Kết quả nhận biết bệnh ── */
window.currentResult = null;     // kết quả của ảnh đang xem (chat dùng làm ngữ cảnh)
let lastTreatmentCls = null;
let imgViews = { orig: null, cam: null };

function setDonut(suffix, infected) {
  const healthy = 100 - infected;
  const infLen = (infected / 100) * DONUT_C;
  const okLen = (healthy / 100) * DONUT_C;
  const gH = $('donutHealthy' + suffix), gI = $('donutInfected' + suffix);
  if (gH) gH.setAttribute('stroke-dasharray', `${okLen} ${DONUT_C}`);
  if (gI) {
    gI.setAttribute('stroke-dasharray', `${infLen} ${DONUT_C}`);
    gI.setAttribute('stroke-dashoffset', `-${okLen}`);
  }
  setText('donutPct' + suffix, infected + '%');
  setText('legHealthy' + suffix, healthy + '%');
  setText('legInfected' + suffix, infected + '%');
}

async function loadTreatment(cls) {
  if (cls === lastTreatmentCls) return;
  lastTreatmentCls = cls;
  const fill = (t) => {
    setText('recFarm', t.canh_tac); setText('recBio', t.sinh_hoc); setText('recChem', t.hoa_hoc);
    setText('solFarm', t.canh_tac); setText('solBio', t.sinh_hoc); setText('solChem', t.hoa_hoc);
  };
  if (!cls || cls === 'not_rice') {
    fill({ canh_tac: 'Chưa có kết quả nhận diện bệnh.', sinh_hoc: '—', hoa_hoc: '—' });
    setText('solTitle', 'Đề xuất xử lý');
    return;
  }
  try {
    const r = await fetch('/api/treatment/' + encodeURIComponent(cls));
    if (!r.ok) return;
    const t = await r.json();
    fill(t);
    setText('solTitle', 'Đề xuất xử lý — ' + t.class_vi);
  } catch (e) { lastTreatmentCls = null; }
}

/* Ảnh kết quả: Grad-CAM (vùng AI chú ý) hoặc ảnh gốc */
function showImgView(view) {
  const img = $('disImg'), svg = $('disSvg'), tog = $('imgToggle');
  const src = imgViews[view] || imgViews.orig || imgViews.cam;
  if (!img || !src) return;
  img.src = src; img.hidden = false; img.style.display = 'block';
  if (svg) svg.style.display = 'none';
  const hasCam = !!imgViews.cam;
  if (tog) {
    tog.hidden = !hasCam;
    tog.querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.view === (imgViews[view] ? view : 'orig')));
  }
}

function resetResultImage() {
  imgViews = { orig: null, cam: null };
  const img = $('disImg'), svg = $('disSvg'), tog = $('imgToggle');
  if (img) { img.hidden = true; img.style.display = 'none'; img.removeAttribute('src'); }
  if (svg) svg.style.display = '';
  if (tog) tog.hidden = true;
}

/* Hiển thị kết quả của 1 ảnh. origUrl: ảnh gốc để so sánh với Grad-CAM. */
function renderResult(d, origUrl) {
  if (!d || !d.class) return;
  window.currentResult = d;
  setText('disName', d.class_vi || '—');
  setText('disConf', (d.confidence ?? 0) + '%');
  setText('disSev', d.severity || '—');
  const bar = $('disBar');
  if (bar) bar.style.width = (d.confidence ?? 0) + '%';

  const infected = Math.max(0, Math.min(100, d.ratio_infected ?? 0));
  setDonut('', infected);
  setDonut('2', infected);
  const lbl = d.class === 'not_rice' ? 'Tỷ lệ so sánh' : `Tỷ lệ so sánh (${d.class_vi || ''})`;
  setText('ratioLbl', lbl);
  setText('ratioLbl2', lbl);

  const t3 = $('top3');
  if (t3) {
    if (d.top3 && d.class !== 'not_rice') {
      t3.hidden = false;
      t3.textContent = 'Khả năng: ' + d.top3.map(x => `${x.class_vi} ${x.p}%`).join(' · ');
    } else { t3.hidden = true; }
  }

  imgViews = { orig: origUrl || d.image || null, cam: d.gradcam || null };
  showImgView(imgViews.cam ? 'cam' : 'orig');
  loadTreatment(d.class);
}

function clearResult() {
  window.currentResult = null;
  lastTreatmentCls = null;
  setText('disName', 'Chưa có ảnh phân tích');
  setText('disConf', '0%'); setText('disSev', '—');
  const bar = $('disBar'); if (bar) bar.style.width = '0%';
  setDonut('', 0); setDonut('2', 0);
  setText('ratioLbl', 'Tỷ lệ so sánh'); setText('ratioLbl2', 'Tỷ lệ so sánh');
  const t3 = $('top3'); if (t3) t3.hidden = true;
  resetResultImage();
  loadTreatment(null);
}

async function loadStats() {
  try {
    const rows = await (await fetch('/api/history?limit=500')).json();
    const sick = rows.filter(x => x.class !== 'normal' && x.class !== 'not_rice').length;
    setText('statTotal', rows.length);
    setText('statDisease', sick);
  } catch (e) { /* bỏ qua */ }
}

/* ── Cảm biến: chưa cắm thiết bị thì báo rõ, không hiển thị số giả ── */
function applyBadge(id, badge) {
  const el = $(id);
  if (!el) return;
  if (!badge) { el.textContent = 'Chưa kết nối'; el.className = 'badge badge-gray'; return; }
  el.textContent = badge.label;
  el.className = 'badge badge-' + (badge.level === 'green' ? 'green' : badge.level === 'red' ? 'red' : 'blue');
}

function setCard(valId, noteId, d, hdrId, hdrUnit) {   // d = {available, value, message, mock}
  const ok = d && d.available && d.value !== undefined;
  setText(valId, ok ? d.value : '—');
  if (hdrId) setText(hdrId, ok ? d.value + hdrUnit : '—');
  setText(noteId, ok ? (d.mock ? 'Dữ liệu giả lập (SENSORS_MOCK=1)' : '') : ((d && d.message) || 'Chưa kết nối cảm biến'));
  return ok;
}

async function pollSensors() {
  try {
    const s = await (await fetch('/api/sensors', { cache: 'no-store' })).json();
    setText('valN', s.n.value);   applyBadge('badgeN', s.n.badge);
    setText('valP', s.p.value);   applyBadge('badgeP', s.p.badge);
    setText('valK', s.k.value);   applyBadge('badgeK', s.k.badge);
    setText('valPh', s.ph.value); applyBadge('badgePh', s.ph.badge);
    const t = setCard('valTemp', 'tempNote', s.temp, 'hdrTemp', '°C');
    const so = s.soil_moisture || {};
    // chưa hiệu chuẩn -> không có %, chỉ hiện điện áp thô trong ghi chú
    setCard('valSoil', 'soilNote', so.calibrated ? so : { available: false, message: so.message }, 'hdrSoil', '%');
    const b = $('sensorBanner'); if (b) b.hidden = t && so.available;
  } catch (e) {
    ['valTemp', 'valSoil', 'hdrTemp', 'hdrSoil'].forEach(id => setText(id, '—'));
    const b = $('sensorBanner'); if (b) b.hidden = false;
  }
}

/* ── Trạng thái hệ thống (thay cho dòng "mọi thứ bình thường" cố định) ── */
async function pollHealth() {
  const box = $('sysBox'), icon = $('sysIcon');
  try {
    const h = await (await fetch('/api/health', { cache: 'no-store' })).json();
    const problems = [];
    if (!h.model_loaded) problems.push('model chưa nạp');
    if (!h.camera) problems.push('camera chưa kết nối');
    const ok = problems.length === 0;
    setText('sysMsg', ok ? 'Hệ thống sẵn sàng' : 'Cần chú ý: ' + problems.join(', '));
    if (icon) icon.innerHTML = `<i class="fas fa-${ok ? 'check' : 'triangle-exclamation'}"></i>`;
    if (box) box.classList.toggle('sys-warn', !ok);
    setText('sysUpd', 'Kiểm tra: ' + new Date().toLocaleTimeString('vi-VN'));
  } catch (e) {
    setText('sysMsg', 'Mất kết nối tới máy chủ');
    if (icon) icon.innerHTML = '<i class="fas fa-circle-xmark"></i>';
    if (box) box.classList.add('sys-warn');
  }
}

/* ── Phóng to ảnh kết quả (bấm vào ảnh) ── */
let lightboxView = 'cam';

function lightboxShow(view) {
  const src = imgViews[view] || imgViews.orig || imgViews.cam;
  if (!src) return;
  lightboxView = imgViews[view] ? view : 'orig';
  $('lightboxImg').src = src;
  $('lightboxToggle').hidden = !imgViews.cam;
  $('lightboxToggle').querySelectorAll('button').forEach(b => b.classList.toggle('active', b.dataset.view === lightboxView));
  const r = window.currentResult;
  $('lightboxCap').textContent = r ? `${r.class_vi} — ${r.confidence}%` +
    (lightboxView === 'cam' ? ' · Vùng đỏ/vàng là nơi AI chú ý nhiều nhất' : '') : '';
}

function openLightbox() {
  if (!imgViews.orig && !imgViews.cam) return;
  lightboxShow(imgViews.cam ? 'cam' : 'orig');
  $('lightbox').hidden = false;
}
function closeLightbox() { $('lightbox').hidden = true; }

document.addEventListener('DOMContentLoaded', function () {
  const di = $('disImg');
  if (di) di.addEventListener('click', openLightbox);
  $('lightbox').addEventListener('click', e => { if (e.target.id === 'lightbox') closeLightbox(); });
  $('lightboxClose').addEventListener('click', closeLightbox);
  $('lightboxToggle').querySelectorAll('button').forEach(b => b.addEventListener('click', () => lightboxShow(b.dataset.view)));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });
});

document.addEventListener('DOMContentLoaded', function () {
  clearResult();
  pollSensors();
  pollHealth();
  loadStats();
  setInterval(pollSensors, SENSOR_MS);
  setInterval(pollHealth, HEALTH_MS);
  setInterval(loadStats, 30000);
  document.querySelectorAll('#imgToggle button').forEach(b =>
    b.addEventListener('click', () => showImgView(b.dataset.view)));
});
