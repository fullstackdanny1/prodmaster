// Chat cu notițele: răspuns doar din notițe, cu citări care deschid secțiunea corectă.
import { $, enhance, esc, modelSelect, noteHref, scopeSelect, send, setView, state, toast } from './util.js';

const history = [];      // doar în memoria paginii: { intrebare, raspuns, raspuns_html, surse }

export async function showChat(params) {
  state.current = '';
  const models = await modelSelect('chModel', 'chat');
  setView(`<section class="sheet chat">
    <h1>Chat cu notițele</h1>
    <p class="lead">Răspunsurile vin doar din notițele tale și din textul surselor importate, cu trimitere la secțiune.</p>
    <div class="grid2">
      <label class="field"><span>Caută în</span>${scopeSelect('chScope', params.get('scope') || state.context)}</label>
      ${models}
    </div>
    <div id="thread" class="thread" aria-live="polite"></div>
    <form id="chForm" class="ask">
      <textarea id="chQ" rows="2" placeholder="Întreabă ceva despre materie… (Enter trimite, Shift+Enter rând nou)" aria-label="Întrebarea"></textarea>
      <button class="btn primary">Întreabă</button>
    </form>
    ${history.length ? '<div class="actions"><button class="link-btn" id="chClear">Conversație nouă</button></div>' : ''}
  </section>`);
  drawThread();
  $('#chQ').focus();
  $('#chForm').addEventListener('submit', (e) => { e.preventDefault(); ask(); });
  $('#chQ').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } });
  $('#chClear')?.addEventListener('click', () => { history.length = 0; showChat(params); });
  $('#thread').addEventListener('click', (e) => { const b = e.target.closest('[data-save]'); if (b) save(Number(b.dataset.save)); });
}

function citeLinks(html, sources) {
  return html.replace(/\[(\d+)\]/g, (m, n) => {
    const s = sources.find((x) => x.n === Number(n));
    if (!s || !s.notita) return m;
    return `<a class="cite" href="${noteHref(s.notita, s.sectiune)}" title="${esc(s.titlu)} — ${esc(s.titlu_sectiune || '')}">[${n}]</a>`;
  });
}

function drawThread() {
  const t = $('#thread');
  t.innerHTML = history.map((h, k) => `<div class="msg q">${esc(h.intrebare)}</div>
    <div class="msg a">${h.pending ? '<p class="meta">Caut în notițe…</p>' : `<div class="prose">${citeLinks(h.raspuns_html, h.surse)}</div>
      ${h.surse.length ? `<ol class="sources">${h.surse.map((s) => `<li>${s.notita ? `<a href="${noteHref(s.notita, s.sectiune)}">${esc(s.titlu)}</a>` : esc(s.titlu)} <span class="muted">— ${esc(s.titlu_sectiune || '')}${s.tip === 'sursa' ? ' (textul sursei)' : ''}</span></li>`).join('')}</ol>` : ''}
      <div class="actions"><button class="link-btn" data-save="${k}">Salvează ca notiță</button></div>`}</div>`).join('');
  t.querySelectorAll('.msg.a .prose').forEach((el) => enhance(el, ''));
  t.lastElementChild?.scrollIntoView({ block: 'nearest' });
}

async function ask() {
  const q = $('#chQ').value.trim();
  if (!q) return;
  const entry = { intrebare: q, pending: true, surse: [] };
  history.push(entry);
  $('#chQ').value = '';
  drawThread();
  try {
    const past = history.filter((h) => !h.pending).slice(-3).map((h) => ({ intrebare: h.intrebare, raspuns: h.raspuns }));
    const r = await send('/api/chat', { intrebare: q, scope: $('#chScope').value, istoric: past, model: $('#chModel')?.value || null });
    Object.assign(entry, r, { pending: false });
  } catch (e) {
    history.pop();
    toast(e.message, 'error');
    $('#chQ').value = q;
  }
  drawThread();
}

async function save(k) {
  const h = history[k];
  const folder = $('#chScope').value;
  try {
    const r = await send('/api/chat/salvare', { intrebare: h.intrebare, raspuns: h.raspuns, surse: h.surse, folder });
    window.dispatchEvent(new Event('studiu:tree'));
    toast('Salvat ca notiță (de revizuit).');
    location.hash = noteHref(r.path);
  } catch (e) { toast(e.message, 'error'); }
}
