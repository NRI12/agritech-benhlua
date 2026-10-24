/* ── Camera: chụp ảnh từ luồng xem trước rồi gửi phân tích ── */

document.addEventListener('DOMContentLoaded', function () {
  const btn = document.getElementById('captureBtn');
  if (!btn) return;
  btn.addEventListener('click', async function () {
    btn.disabled = true;
    const old = btn.innerHTML;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Đang chụp & phân tích...';
    try {
      await window.analyzeCapture();
    } finally {
      btn.disabled = false;
      btn.innerHTML = old;
    }
  });
});
