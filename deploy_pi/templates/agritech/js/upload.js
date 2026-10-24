/* ── Chọn / kéo thả / dán ảnh, hoặc chụp từ camera, để phân tích ── */

document.addEventListener('DOMContentLoaded', function () {
  const input = document.getElementById('imgInput');
  const pick = document.getElementById('pickBtn');
  const zone = document.getElementById('dropZone');
  const state = document.getElementById('uploadState');
  const msg = document.getElementById('uploadMsg');
  const clearBtn = document.getElementById('backCamBtn');
  let objUrl = null;

  function begin(text) {
    state.hidden = false;
    msg.textContent = text;
    if (typeof setTab === 'function') setTab('detect', document.querySelector('.tab-btn'));
  }

  // Ảnh mới = ngữ cảnh mới: xoá cuộc trò chuyện cũ để AI không trả lời theo ảnh trước
  function finish(d, label, origUrl) {
    msg.textContent = 'Kết quả cho: ' + label;
    renderResult(d, origUrl);
    if (typeof chatReset === 'function') {
      chatReset(d.class === 'not_rice'
        ? 'Ảnh vừa phân tích không phải hình ảnh lúa. Hãy chụp hoặc chọn ảnh lá lúa rõ nét.'
        : `Đã phân tích ảnh mới: ${d.class_vi} (độ tin cậy ${d.confidence}%). Bạn có thể hỏi tôi về kết quả này.`);
    }
    if (typeof loadStats === 'function') loadStats();
  }

  async function post(url, opts) {
    const res = await fetch(url, opts);
    const d = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(d.error || 'Phân tích thất bại.');
    return d;
  }

  async function analyzeFile(file) {
    if (!file || !file.type.startsWith('image/')) { alert('Hãy chọn một file ảnh (JPG, PNG).'); return; }
    if (file.size > 10 * 1024 * 1024) { alert('Ảnh quá lớn (tối đa 10 MB).'); return; }
    begin('Đang phân tích ' + file.name + '...');
    if (objUrl) URL.revokeObjectURL(objUrl);
    objUrl = URL.createObjectURL(file);
    const fd = new FormData();
    fd.append('image', file);
    try {
      finish(await post('/api/predict/image', { method: 'POST', body: fd }), file.name, objUrl);
    } catch (e) { msg.textContent = e.message; }
  }

  window.analyzeCapture = async function () {
    begin('Đang chụp ảnh từ camera...');
    try {
      const d = await post('/api/capture', { method: 'POST' });
      finish(d, 'ảnh chụp từ camera', d.image);
    } catch (e) { msg.textContent = e.message; }
  };

  pick.addEventListener('click', () => input.click());
  input.addEventListener('change', () => { analyzeFile(input.files[0]); input.value = ''; });
  clearBtn.addEventListener('click', () => {
    state.hidden = true;
    clearResult();
    if (typeof chatReset === 'function') chatReset();
  });

  ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('drag'); }));
  ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove('drag'); }));
  zone.addEventListener('drop', e => analyzeFile(e.dataTransfer.files[0]));
  document.addEventListener('paste', e => {
    const f = [...(e.clipboardData?.files || [])].find(x => x.type.startsWith('image/'));
    if (f) analyzeFile(f);
  });
});
