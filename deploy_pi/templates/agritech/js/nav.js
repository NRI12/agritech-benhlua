/* ── Sidebar navigation: chuyển trang thật ── */

function setNav(el) {
  document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
  el.classList.add('active');
}

function showPage(page, el) {
  if (el) setNav(el);
  const main = document.getElementById('mainContent');
  if (main) main.dataset.page = page;
  try { history.replaceState(null, '', '#' + page); } catch (e) { /* bỏ qua */ }
  if (typeof loadPage === 'function') loadPage(page);
}

document.addEventListener('DOMContentLoaded', function () {
  const p = (location.hash || '').slice(1);
  const el = p && document.querySelector(`.nav-item[data-page="${p}"]`);
  if (el) showPage(p, el);
});
