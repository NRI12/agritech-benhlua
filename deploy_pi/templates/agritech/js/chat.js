/* ── AI Chat feature ── */

document.addEventListener('DOMContentLoaded', function () {
  const chatMsgs = document.getElementById('chatMsgs');
  const chatIn   = document.getElementById('chatIn');
  const sendBtn  = document.getElementById('sendBtn');

  function now() {
    const d = new Date();
    return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  }

  function appendMsg(text, isUser) {
    const div = document.createElement('div');
    div.className = 'msg ' + (isUser ? 'user' : 'ai');
    // text có thể chứa xuống dòng -> đổi \n thành <br>
    // Escape HTML trước (chống chèn mã), rồi mới hiển thị **đậm** và xuống dòng
    const html = String(text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>')
      .replace(/^(\s*)[-*] /gm, '$1• ')
      .replace(/\n/g, '<br>');
    div.innerHTML = isUser
      ? `<div class="msg-bub">${html}<span class="msg-time">${now()}</span></div>`
      : `<div class="msg-av">AI</div><div class="msg-bub">${html}<span class="msg-time">${now()}</span></div>`;
    chatMsgs.appendChild(div);
    chatMsgs.scrollTop = chatMsgs.scrollHeight;
    return div;
  }

  // Lịch sử hội thoại gửi kèm mỗi câu hỏi để AI hiểu ngữ cảnh (không gồm lời chào/demo ban đầu)
  const history = [];
  const DISCLAIMER = /\n*Lưu ý: Kết quả AI chỉ mang tính tham khảo[^\n]*$/;

  async function sendMsg(preset) {
    const txt = (typeof preset === 'string' ? preset : chatIn.value).trim();
    if (!txt) return;
    appendMsg(txt, true);
    chatIn.value = '';

    const thinking = appendMsg('Đang phân tích...', false);
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: txt,
          history: history.slice(-24),
          // Ngữ cảnh = kết quả của ảnh đang xem (không phải kết quả cũ nào khác)
          context: window.currentResult
            ? { class: window.currentResult.class, confidence: window.currentResult.confidence } : null
        })
      });
      const data = await res.json();
      thinking.remove();
      const reply = data.reply || 'Xin lỗi, tôi chưa có câu trả lời.';
      appendMsg(reply, false);
      if (data.reply) {
        history.push({ role: 'user', content: txt },
                     { role: 'assistant', content: reply.replace(DISCLAIMER, '').trim() });
      }
    } catch (e) {
      thinking.remove();
      appendMsg('Không kết nối được tới máy chủ. Kiểm tra backend đang chạy chưa nhé.', false);
    }
  }

  // ── Cài đặt API key ChatGPT (áp dụng ngay, không cần restart) ──
  function adminHeaders() {
    const h = { 'Content-Type': 'application/json' };
    const t = sessionStorage.getItem('adminToken');
    if (t) h['X-Admin-Token'] = t;
    return h;
  }

  async function keyRequest(method, body) {
    let res = await fetch('/api/settings/api-key', {
      method, headers: adminHeaders(), cache: 'no-store',
      body: body ? JSON.stringify(body) : undefined
    });
    if (res.status === 403) {
      const t = prompt('Cần mã quản trị (ADMIN_TOKEN) để đổi API key:');
      if (!t) return null;
      sessionStorage.setItem('adminToken', t);
      res = await fetch('/api/settings/api-key', {
        method, headers: adminHeaders(), cache: 'no-store',
        body: body ? JSON.stringify(body) : undefined
      });
    }
    return res;
  }

  async function configureKey() {
    try {
      const st = await keyRequest('GET');
      if (!st) return;
      const info = await st.json();
      if (!st.ok) { alert(info.error || 'Không có quyền.'); return; }
      const cur = info.configured ? `Key hiện tại: ${info.masked} (nguồn: ${info.source}).\n` : 'Chưa có API key.\n';
      const v = prompt(cur + 'Dán API key OpenAI mới (để trống = giữ nguyên, gõ "xoa" = xoá key):');
      if (v === null || v.trim() === '') return;
      const res = v.trim().toLowerCase() === 'xoa'
        ? await keyRequest('DELETE')
        : await keyRequest('POST', { key: v.trim() });
      if (!res) return;
      const out = await res.json();
      if (!res.ok) { alert(out.error || 'Lỗi lưu key.'); return; }
      appendMsg(out.configured ? `Đã cập nhật API key (${out.masked}). Áp dụng ngay cho câu hỏi tiếp theo.`
                               : 'Đã xoá API key. Chatbot dùng tư vấn có sẵn.', false);
    } catch (e) {
      alert('Không kết nối được tới máy chủ.');
    }
  }

  document.getElementById('keyBtn').addEventListener('click', configureKey);
  // ── Câu hỏi gợi ý: bấm để gửi, thay đổi theo kết quả ảnh đang xem ──
  const SUGGEST = {
    none: ['Các bệnh lúa phổ biến là gì?', 'Chụp ảnh lá lúa thế nào cho chính xác?',
           'Cách phòng bệnh cho ruộng lúa?', 'Khi nào nên phun thuốc?'],
    normal: ['Làm sao để phòng bệnh cho lúa?', 'Bón phân N-P-K thế nào cho cân đối?',
             'Bao lâu nên kiểm tra ruộng một lần?', 'Tôi có cần phun thuốc không?'],
    disease: ['Đây là bệnh gì, nguyên nhân do đâu?', 'Cách xử lý bệnh này?',
              'Có biện pháp không dùng thuốc hoá học không?', 'Nên phun thuốc lúc nào, bao lâu phun lại?',
              'Bệnh này có lây sang ruộng khác không?', 'Phun thuốc cần lưu ý an toàn gì?']
  };

  function renderSuggest() {
    const box = document.getElementById('chatSuggest');
    if (!box) return;
    const r = window.currentResult;
    const key = !r || r.class === 'not_rice' ? 'none' : r.class === 'normal' ? 'normal' : 'disease';
    box.innerHTML = '';
    SUGGEST[key].forEach(q => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'suggest-chip'; b.textContent = q;
      b.addEventListener('click', () => sendMsg(q));
      box.appendChild(b);
    });
  }
  window.renderSuggest = renderSuggest;

  // Xoá cuộc trò chuyện (và lịch sử gửi cho AI); note: lời nhắn đầu tiên sau khi xoá
  window.chatReset = function (note) {
    history.length = 0;
    chatMsgs.innerHTML = '';
    appendMsg(note || 'Đã xoá cuộc trò chuyện. Hãy chụp hoặc chọn ảnh lá lúa để phân tích, rồi hỏi tôi nhé.', false);
    renderSuggest();
  };
  document.getElementById('clearChatBtn').addEventListener('click', () => window.chatReset());

  sendBtn.addEventListener('click', () => sendMsg());
  chatIn.addEventListener('keydown', e => { if (e.key === 'Enter') sendMsg(); });

  chatMsgs.scrollTop = chatMsgs.scrollHeight;
  renderSuggest();
});
