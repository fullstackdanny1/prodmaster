// Utilitare comune interfeței: API, mesaje, formule, diagrame, selectoare.

export const $ = (s, el = document) => el.querySelector(s);
export const $$ = (s, el = document) => [...el.querySelectorAll(s)];
export const main = () => $('#main');
export const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
export const enc = (p) => encodeURIComponent(p);
export const displayName = (n) => n.replace(/\.md$/i, '').replace(/^\d+[\s._-]+(?=\S)/, '');
export const parentDir = (p) => (p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '');
export const ancestors = (p) => p.split('/').slice(0, -1).map((_, i, a) => a.slice(0, i + 1).join('/'));
export const plural = (n, one, many) => (n === 1 ? `1 ${one}` : `${n} ${many}`);

export const store = {
  get(k, d) { try { const v = localStorage.getItem('studiu.' + k); return v ? JSON.parse(v) : d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem('studiu.' + k, JSON.stringify(v)); } catch { /* fără stocare */ } },
};

// Starea comună tuturor ecranelor.
export const state = {
  tree: null,
  expanded: new Set(store.get('expanded', [])),
  current: '',
  context: '',
  dirty: false,
  editHash: null,
  edit: null,
  note: null,
  cleanup: null,     // funcție apelată la părăsirea ecranului (cronometre, taste)
};

export async function api(url, opts = {}) {
  const headers = opts.body instanceof FormData ? {} : { 'Content-Type': 'application/json' };
  const r = await fetch(url, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch { /* răspuns fără JSON */ }
    if (typeof msg !== 'string') msg = JSON.stringify(msg);
    const err = new Error(msg);
    err.status = r.status;
    throw err;
  }
  return r.json();
}
export const send = (url, body, method = 'POST') => api(url, { method, body: JSON.stringify(body) });

export function toast(msg, kind = '') {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast ' + kind;
  t.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => { t.hidden = true; }, kind === 'error' ? 6000 : 3200);
}

export function setView(html) {
  main().innerHTML = html;
  main().scrollTop = 0;
}

export function noteHref(path, anchor = '') {
  return '#/n/' + enc(path) + (anchor ? '?s=' + enc(anchor) : '');
}

/* ---------- formule ---------- */

export function typeset(el) {
  if (!window.katex) return;
  el.querySelectorAll('.math').forEach((m) => {
    try {
      window.katex.render(m.textContent.trim(), m, { displayMode: m.classList.contains('block'), throwOnError: false });
    } catch { /* formula rămâne ca text */ }
  });
}

// Text simplu cu formule $...$ / $$...$$ (întrebările și răspunsurile cardurilor).
export function richText(s) {
  const parts = String(s ?? '').split(/(\$\$[\s\S]+?\$\$|\$[^$\n]+?\$)/g);
  return parts.map((p) => {
    const block = p.startsWith('$$') && p.endsWith('$$') && p.length > 4;
    const inline = !block && p.startsWith('$') && p.endsWith('$') && p.length > 2;
    if ((block || inline) && window.katex) {
      try {
        return window.katex.renderToString(block ? p.slice(2, -2) : p.slice(1, -1), { displayMode: block, throwOnError: false });
      } catch { /* cade pe text */ }
    }
    return esc(p).replace(/\n/g, '<br>');
  }).join('');
}

/* ---------- diagrame Mermaid (încărcate doar când pagina are diagrame) ---------- */

let mermaidLoading = null;
let mermaidCounter = 0;

function loadMermaid() {
  if (window.mermaid) return Promise.resolve(window.mermaid);
  if (!mermaidLoading) {
    mermaidLoading = new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = '/static/vendor/mermaid/mermaid.min.js';
      s.onload = () => {
        const dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        window.mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'default' });
        resolve(window.mermaid);
      };
      s.onerror = () => { mermaidLoading = null; reject(new Error('Nu pot încărca Mermaid')); };
      document.head.appendChild(s);
    });
  }
  return mermaidLoading;
}

export async function renderMermaid(el) {
  const nodes = [...el.querySelectorAll('div.mermaid:not([data-done])')];
  if (!nodes.length) return;
  let m;
  try { m = await loadMermaid(); } catch { return; }
  for (const node of nodes) {
    const src = node.textContent;
    node.dataset.done = '1';
    try {
      const { svg } = await m.render('mmd-' + (++mermaidCounter), src);
      node.innerHTML = svg;
    } catch (e) {
      node.classList.add('mermaid-error');
      node.innerHTML = `<pre>${esc(src)}</pre><p class="error-line">Diagramă cu erori: ${esc(String(e.message || e).split('\n')[0])}</p>`;
      document.getElementById('dmmd-' + mermaidCounter)?.remove();
    }
  }
}

/* ---------- linkuri și imagini relative ---------- */

export function resolveRel(baseDir, rel) {
  const parts = baseDir ? baseDir.split('/') : [];
  for (const seg of decodeURIComponent(rel).split('/')) {
    if (seg === '..') parts.pop();
    else if (seg && seg !== '.') parts.push(seg);
  }
  return parts.join('/');
}

export function enhance(el, baseDir) {
  typeset(el);
  renderMermaid(el);
  el.querySelectorAll('a[href]').forEach((a) => {
    const href = a.getAttribute('href');
    if (/^[a-z][a-z0-9+.-]*:/i.test(href)) { a.target = '_blank'; a.rel = 'noopener'; return; }
    if (href.startsWith('#/')) return;
    if (href.startsWith('#')) { a.dataset.anchor = href.slice(1); return; }
    const [file, anchor] = href.split('#');
    const target = resolveRel(baseDir, file);
    if (/\.md$/i.test(target)) a.setAttribute('href', noteHref(target, anchor ? decodeURIComponent(anchor) : ''));
    else { a.setAttribute('href', '/api/fisier?path=' + enc(target)); a.target = '_blank'; }
  });
  el.querySelectorAll('img[src]').forEach((img) => {
    const src = img.getAttribute('src');
    if (!/^[a-z][a-z0-9+.-]*:/i.test(src)) img.src = '/api/fisier?path=' + enc(resolveRel(baseDir, src));
  });
}

/* ---------- selectoare ---------- */

export function folderList(node = state.tree, out = [], depth = 0) {
  if (!node) return out;
  for (const c of node.children) {
    if (c.type !== 'dir') continue;
    out.push({ path: c.path, name: c.name, depth, count: c.count });
    folderList(c, out, depth + 1);
  }
  return out;
}

export function scopeSelect(id, selected = '', allLabel = 'Toate notițele') {
  const opts = folderList().map((f) => `<option value="${esc(f.path)}"${f.path === selected ? ' selected' : ''}>${'  '.repeat(f.depth)}${f.depth ? '└ ' : ''}${esc(f.name)}</option>`);
  return `<select id="${id}" class="select"><option value="">${esc(allLabel)}</option>${opts.join('')}</select>`;
}

let modelsCache = null;
export async function models() {
  if (!modelsCache) modelsCache = await api('/api/ai/modele').catch(() => null);
  return modelsCache;
}

// Selectorul opțional „Model”: aliasurile și modelele configurate, cu implicitul sarcinii preselectat.
export async function modelSelect(id, task) {
  const m = await models();
  if (!m) return '';
  const def = m.implicit_sarcini?.[task] || '';
  const tag = (ref) => {
    const prov = m.furnizori[(ref || '').split(':')[0]];
    if (!prov) return '';
    return prov.local ? ' (local)' : prov.gratuit ? ' (gratuit)' : '';
  };
  const seen = new Set();
  const opts = [`<option value="">Implicit: ${esc(def)}${tag(def)}</option>`];
  for (const [alias, v] of Object.entries(m.aliasuri || {})) {
    opts.push(`<option value="${esc(alias)}">${esc(alias)} → ${esc(v.rezolvat)}${tag(v.rezolvat)}</option>`);
    seen.add(v.rezolvat);
  }
  for (const v of Object.values(m.sarcini || {})) {
    if (!seen.has(v.rezolvat) && !v.rezolvat.startsWith('eroare')) {
      seen.add(v.rezolvat);
      opts.push(`<option value="${esc(v.rezolvat)}">${esc(v.rezolvat)}${tag(v.rezolvat)}</option>`);
    }
  }
  return `<label class="field small"><span>Model</span><select id="${id}" class="select">${opts.join('')}</select></label>`;
}

export function costText(e) {
  if (!e) return '';
  if (e.eroare_ai) return `AI neconfigurat: ${e.eroare_ai}`;
  const tokens = `~${(e.tokeni_intrare || 0).toLocaleString('ro-RO')} tokeni trimiși, ~${(e.tokeni_iesire || 0).toLocaleString('ro-RO')} primiți`;
  const cost = e.gratuit || !e.cost_usd ? 'gratuit' : `~${e.cost_usd.toFixed(3)} USD`;
  return `${tokens} · ${cost}${e.model ? ` · ${e.model}` : ''}`;
}

export function fmtDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleString('ro-RO', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}
