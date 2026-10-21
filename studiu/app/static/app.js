// Studiu: navigarea pe hash și ecranele bibliotecii. Celelalte ecrane sunt în module separate.
import {
  $, ancestors, api, displayName, enc, enhance, esc, main, noteHref, parentDir, plural, send, setView,
  state, store, toast,
} from './util.js';
import { cardsPanel, orphansSection } from './cards.js';
import { showImport } from './import.js';
import { showReviewStart, showReviewSession } from './review.js';
import { showQuiz, showExam, showExamResult } from './quiz.js';
import { showChat } from './chat.js';
import { showSettings } from './settings.js';

/* ---------- arbore ---------- */

export async function loadTree() {
  const d = await api('/api/arbore');
  state.tree = d.tree;
  renderTree();
  const pill = $('#revCount');
  pill.textContent = d.tree.unverified;
  pill.hidden = !d.tree.unverified;
}

function findNode(path, node = state.tree) {
  if (!node) return null;
  if (node.path === path) return node;
  if (node.type !== 'dir') return null;
  for (const c of node.children) {
    const f = findNode(path, c);
    if (f) return f;
  }
  return null;
}

function allNotes(node = state.tree, out = []) {
  for (const c of node.children) (c.type === 'dir' ? allNotes(c, out) : out.push(c));
  return out;
}

function expandTo(path, includeSelf = false) {
  ancestors(path).forEach((p) => state.expanded.add(p));
  if (includeSelf) state.expanded.add(path);
  store.set('expanded', [...state.expanded]);
}

function renderTree() {
  const t = $('#tree');
  if (!state.tree) return;
  if (!state.tree.children.length) {
    t.innerHTML = '<p class="empty-small">Nicio materie încă. Adaug-o pe prima cu „+ Materie”.</p>';
    return;
  }
  t.innerHTML = '<ul role="tree">' + state.tree.children.map(treeItem).join('') + '</ul>';
}

function treeItem(n) {
  const active = n.path === state.current ? ' active' : '';
  if (n.type === 'note') {
    const dot = n.unverified ? '<span class="dot" title="Generată de AI, nerevizuită"></span>' : '';
    return `<li role="treeitem"><a class="t-note${active}" href="#/n/${enc(n.path)}" title="${esc(n.title)}">${dot}<span class="t-label">${esc(n.title)}</span></a></li>`;
  }
  const open = state.expanded.has(n.path);
  const kids = open ? `<ul role="group">${n.children.map(treeItem).join('')}</ul>` : '';
  return `<li role="treeitem" aria-expanded="${open}">
    <div class="t-dir${active}">
      <button class="caret" data-toggle="${esc(n.path)}" aria-label="${open ? 'Restrânge' : 'Extinde'} ${esc(n.name)}">${open ? '▾' : '▸'}</button>
      <a href="#/d/${enc(n.path)}" class="t-label">${esc(n.name)}</a>
      <span class="t-count">${n.count}</span>
    </div>${kids}</li>`;
}

/* ---------- randare de bază ---------- */

function crumbsHtml(crumbs, last = '') {
  const parts = [`<a href="#/">Notițe</a>`, ...crumbs.map((c) => `<a href="#/d/${enc(c.path)}">${esc(c.name)}</a>`)];
  if (last) parts.push(`<strong>${esc(last)}</strong>`);
  return parts.join('<span class="sep">/</span>');
}

function pathText(path) {
  return ancestors(path).map((p) => displayName(p.split('/').pop())).join(' / ');
}

export function noteList(notes) {
  if (!notes.length) return '';
  return '<ul class="note-list">' + notes.map((n) => `
    <li><a class="row" href="#/n/${enc(n.path)}">
      <span class="stack"><span class="title">${esc(n.title)}</span>${n.path.includes('/') ? `<span class="path">${esc(pathText(n.path))}</span>` : ''}</span>
      ${n.unverified ? '<span class="tag-ai">De revizuit</span>' : ''}
    </a></li>`).join('') + '</ul>';
}

function topicList(dirs) {
  if (!dirs.length) return '';
  return '<ul class="topic-list">' + dirs.map((d) => `
    <li><a href="#/d/${enc(d.path)}"><strong>${esc(d.name)}</strong>
      <span class="sub">${plural(d.count, 'notiță', 'notițe')}${d.unverified ? `, ${d.unverified} de revizuit` : ''}</span></a></li>`).join('') + '</ul>';
}

/* ---------- ecrane ---------- */

function showHome() {
  state.current = ''; state.context = '';
  const notes = allNotes();
  const dirs = state.tree.children.filter((c) => c.type === 'dir');
  const rootNotes = state.tree.children.filter((c) => c.type === 'note');
  if (!notes.length && !dirs.length) {
    setView(`<section class="sheet">
      <h1>Începe cu o materie</h1>
      <p class="lead">Fiecare materie e un folder, iar fiecare curs sau seminar e o notiță Markdown. Poți crea materii de aici, poți importa un PDF sau poți copia direct folderele tale în folderul de notițe.</p>
      <div class="actions"><button class="btn primary" data-act="new-folder">Adaugă o materie</button><a class="btn" href="#/import">Importă un material</a></div>
    </section>`);
    return;
  }
  const recent = [...notes].sort((a, b) => b.mtime - a.mtime).slice(0, 8);
  const rev = state.tree.unverified;
  setView(`<section class="sheet">
    <h1>Notițele tale</h1>
    <p class="lead">${plural(notes.length, 'notiță', 'notițe')} în ${plural(dirs.length, 'materie', 'materii')}.${rev ? ` <a href="#/revizuit">${rev === 1 ? '1 notiță așteaptă' : rev + ' notițe așteaptă'} revizuirea</a>.` : ''}</p>
    <div class="actions"><a class="btn primary" href="#/repetitie">Repetiția de azi</a><a class="btn" href="#/import">Importă</a></div>
    <h2 class="section">Materii</h2>
    ${topicList(dirs) || '<p class="empty">Nicio materie încă.</p>'}
    ${rootNotes.length ? `<h2 class="section">Notițe fără materie</h2>${noteList(rootNotes)}` : ''}
    <h2 class="section">Modificate recent</h2>
    ${noteList(recent)}
  </section>`);
}

function showDir(path) {
  const node = findNode(path);
  if (!node || node.type !== 'dir') throw Object.assign(new Error('Topicul nu există. Poate a fost redenumit sau mutat.'), { status: 404 });
  state.current = path; state.context = path;
  expandTo(path, true);
  const dirs = node.children.filter((c) => c.type === 'dir');
  const notes = node.children.filter((c) => c.type === 'note');
  const crumbs = ancestors(path).map((p) => ({ path: p, name: displayName(p.split('/').pop()) }));
  setView(`<section class="sheet">
    <nav class="crumbs" aria-label="Cale">${crumbsHtml(crumbs)}</nav>
    <div class="head-row">
      <h1>${esc(node.name)}</h1>
      <div class="actions">
        <button class="btn" data-act="new-folder">Subtopic nou</button>
        <button class="btn primary" data-act="new-note">Notiță nouă</button>
        ${moreMenu()}
      </div>
    </div>
    <p class="meta">${plural(node.count, 'notiță', 'notițe')}${node.unverified ? `, ${node.unverified} de revizuit` : ''}</p>
    <div class="actions"><a class="btn" href="#/repetitie/sesiune?scope=${enc(path)}">Repetă cardurile</a>
      <a class="btn" href="#/quiz?scope=${enc(path)}">Quiz</a><a class="btn" href="#/examen?scope=${enc(path)}">Examen</a></div>
    ${dirs.length ? `<h2 class="section">Subtopicuri</h2>${topicList(dirs)}` : ''}
    ${notes.length ? `<h2 class="section">${dirs.length ? 'Notițe' : 'Lecții și seminarii'}</h2>${noteList(notes)}` : ''}
    ${!dirs.length && !notes.length ? '<p class="empty">Topicul e gol. Creează prima notiță sau împarte-l în subtopicuri.</p>' : ''}
  </section>`);
}

function moreMenu() {
  return `<details class="menu"><summary class="btn" aria-label="Mai multe acțiuni">…</summary>
    <div class="menu-items">
      <button data-act="rename">Redenumește</button>
      <button data-act="move">Mută</button>
      <button data-act="trash" class="danger">Șterge</button>
    </div></details>`;
}

async function showNote(path, section) {
  const n = await api('/api/notita?path=' + enc(path));
  state.note = n;
  state.current = n.path; state.context = parentDir(n.path);
  expandTo(n.path);
  setView(`<article class="sheet">
    <div class="note-bar">
      <nav class="crumbs" aria-label="Cale">${crumbsHtml(n.crumbs)}</nav>
      <div class="actions">
        <button class="btn" data-act="edit" title="Editează (E)">Editează</button>
        ${moreMenu()}
      </div>
    </div>
    ${n.unverified ? `<div class="review-banner">
      <p><strong>Generată de AI, nerevizuită.</strong> Verifică informațiile și corectează ce e greșit; abia apoi notița va fi folosită pentru carduri și quiz-uri.</p>
      <button class="btn primary" data-act="verify">Marchează ca verificată</button>
    </div>` : ''}
    ${n.has_h1 ? '' : `<h1>${esc(n.title)}</h1>`}
    <div class="prose">${n.html}</div>
    <div id="cardsPanel"></div>
  </article>`);
  enhance($('.prose', main()), parentDir(n.path));
  cardsPanel($('#cardsPanel'), n).catch((e) => toast(e.message, 'error'));
  if (section) {
    const target = document.getElementById(section);
    if (target) {
      target.scrollIntoView({ block: 'start' });
      target.classList.add('flash');
    }
  }
}

async function showEdit(path) {
  const n = await api('/api/notita?path=' + enc(path));
  state.current = n.path; state.context = parentDir(n.path);
  state.edit = { path: n.path, mtime: n.mtime };
  state.editHash = location.hash;
  state.dirty = false;
  expandTo(n.path);
  setView(`<section class="editor">
    <div class="editor-bar">
      <nav class="crumbs" aria-label="Cale">${crumbsHtml(n.crumbs, n.title)}</nav>
      <div class="actions">
        <span id="saveState" class="save-state">Salvat</span>
        <button class="btn" data-act="close-edit">Închide</button>
        <button class="btn primary" data-act="save" title="Salvează (Ctrl+S)">Salvează</button>
      </div>
    </div>
    <div class="editor-panes">
      <textarea id="src" spellcheck="true" lang="ro" aria-label="Textul notiței în Markdown"></textarea>
      <div class="preview sheet"><div class="prose" id="pv"></div></div>
    </div>
  </section>`);
  const src = $('#src');
  src.value = n.raw;
  $('#pv').innerHTML = n.html;
  enhance($('#pv'), parentDir(n.path));
  src.focus();
  src.setSelectionRange(0, 0);
}

let previewTimer;
function onEditorInput() {
  state.dirty = true;
  const s = $('#saveState');
  s.textContent = 'Modificări nesalvate';
  s.classList.add('dirty');
  clearTimeout(previewTimer);
  previewTimer = setTimeout(async () => {
    const src = $('#src');
    if (!src) return;
    try {
      const r = await send('/api/randare', { content: src.value });
      const pv = $('#pv');
      if (pv) { pv.innerHTML = r.html; enhance(pv, parentDir(state.edit.path)); }
    } catch { /* previzualizarea se reia la următoarea modificare */ }
  }, 300);
}

async function saveEdit(force = false) {
  const src = $('#src');
  if (!src || !state.edit) return;
  try {
    const r = await send('/api/notita', { path: state.edit.path, content: src.value, mtime: state.edit.mtime, force }, 'PUT');
    state.edit.mtime = r.mtime;
    if (r.raw && r.raw !== src.value) {
      // serverul a adăugat id-ul notiței în antet: păstrăm poziția cursorului
      const delta = r.raw.length - src.value.length;
      const pos = src.selectionStart;
      src.value = r.raw;
      src.setSelectionRange(pos + delta, pos + delta);
    }
    state.dirty = false;
    const s = $('#saveState');
    s.textContent = 'Salvat';
    s.classList.remove('dirty');
    toast('Notița a fost salvată.');
    loadTree();
  } catch (e) {
    if (e.status === 409) {
      if (confirm('Notița a fost modificată în alt editor după ce ai deschis-o. O suprascrii cu versiunea de aici?')) return saveEdit(true);
      return;
    }
    toast('Nu am putut salva: ' + e.message, 'error');
  }
}

async function showSearch(q, scope) {
  $('#q').value = q;
  state.current = '';
  const { results, relaxed } = await api(`/api/cautare?q=${enc(q)}&scope=${enc(scope)}`);
  const scopeName = scope ? displayName(scope.split('/').pop()) : '';
  const narrow = !scope && state.context && results.length > 1
    ? `<a href="#/cauta?q=${enc(q)}&in=${enc(state.context)}">Caută doar în ${esc(displayName(state.context.split('/').pop()))}</a>` : '';
  const found = results.length === 1 ? '1 notiță găsită' : results.length + ' notițe găsite';
  const scopeLine = (scope
    ? `${found} în ${esc(scopeName)}. <a href="#/cauta?q=${enc(q)}">Caută în toate notițele</a>`
    : `${found}. ${narrow}`) + (relaxed && results.length ? '<br>Nu am găsit forma exactă, așa că am inclus forme apropiate ale cuvintelor.' : '');
  setView(`<section class="sheet">
    <h1>Rezultate pentru „${esc(q)}”</h1>
    <p class="meta">${scopeLine}</p>
    ${results.length ? '<ul class="note-list">' + results.map((r) => `
      <li><a class="row" href="#/n/${enc(r.path)}">
        <span class="stack">
          <span class="title">${r.title_html}</span>
          ${r.crumbs.length ? `<span class="path">${esc(r.crumbs.map((c) => c.name).join(' / '))}</span>` : ''}
          <p class="snippet">${r.snippet_html}</p>
        </span>
        ${r.unverified ? '<span class="tag-ai">De revizuit</span>' : ''}
      </a></li>`).join('') + '</ul>'
    : `<p class="empty">Nicio notiță nu conține „${esc(q)}”. Încearcă un termen mai scurt: căutarea găsește și începuturi de cuvinte și ignoră diacriticele.</p>`}
  </section>`);
}

async function showReview() {
  state.current = ''; state.context = '';
  const notes = allNotes().filter((n) => n.unverified);
  setView(`<section class="sheet">
    <h1>De revizuit</h1>
    <p class="lead">Notițele generate de AI rămân aici până le citești și le marchezi ca verificate. Doar notițele verificate sunt folosite pentru carduri și quiz-uri.</p>
    ${notes.length ? noteList(notes) : '<p class="empty">Nicio notiță de revizuit.</p>'}
    <div id="orphans"></div>
  </section>`);
  await orphansSection($('#orphans'));
}

function showError(e) {
  setView(`<section class="sheet">
    <h1>${e.status === 404 ? 'Nu am găsit pagina' : 'Ceva nu a mers'}</h1>
    <p class="lead">${esc(e.message)}</p>
    <div class="actions"><a class="btn" href="#/">Înapoi la notițe</a></div>
  </section>`);
}

/* ---------- navigare ---------- */

export function parseHash() {
  const h = location.hash.slice(1) || '/';
  const qi = h.indexOf('?');
  const route = qi < 0 ? h : h.slice(0, qi);
  const params = new URLSearchParams(qi < 0 ? '' : h.slice(qi + 1));
  const tail = (n) => decodeURIComponent(route.slice(n));
  if (route.startsWith('/n/')) return { view: 'note', tab: 'biblioteca', path: tail(3), section: params.get('s') || '' };
  if (route.startsWith('/e/')) return { view: 'edit', tab: 'biblioteca', path: tail(3) };
  if (route.startsWith('/d/')) return { view: 'dir', tab: 'biblioteca', path: tail(3) };
  if (route === '/cauta') return { view: 'search', tab: '', q: params.get('q') || '', scope: params.get('in') || '' };
  if (route === '/revizuit') return { view: 'review', tab: 'revizuit' };
  if (route === '/import') return { view: 'import', tab: 'import' };
  if (route === '/repetitie') return { view: 'srs', tab: 'repetitie', params };
  if (route === '/repetitie/sesiune') return { view: 'srs-session', tab: 'repetitie', params };
  if (route === '/quiz') return { view: 'quiz', tab: 'quiz', params };
  if (route === '/examen') return { view: 'exam', tab: 'examen', params };
  if (route.startsWith('/examen/')) return { view: 'exam-result', tab: 'examen', id: tail(8) };
  if (route === '/chat') return { view: 'chat', tab: 'chat', params };
  if (route === '/setari') return { view: 'settings', tab: 'setari' };
  return { view: 'home', tab: 'biblioteca' };
}

async function route() {
  if (state.dirty && location.hash !== state.editHash) {
    if (!confirm('Ai modificări nesalvate. Renunți la ele?')) {
      history.replaceState(null, '', state.editHash);
      return;
    }
    state.dirty = false;
  }
  if (state.cleanup) {
    const stop = state.cleanup;
    state.cleanup = null;
    if (stop() === false) return;
  }
  if (location.hash !== state.editHash) state.edit = null;
  document.body.classList.remove('nav-open');
  const r = parseHash();
  document.querySelectorAll('.tabs a').forEach((a) => a.classList.toggle('on', a.dataset.tab === r.tab));
  document.querySelector('.tabs a.on')?.scrollIntoView({ inline: 'nearest', block: 'nearest' });
  if (r.view !== 'note') state.note = null;
  try {
    if (r.view === 'note') await showNote(r.path, r.section);
    else if (r.view === 'edit') await showEdit(r.path);
    else if (r.view === 'dir') showDir(r.path);
    else if (r.view === 'search') await showSearch(r.q, r.scope);
    else if (r.view === 'review') await showReview();
    else if (r.view === 'import') await showImport();
    else if (r.view === 'srs') await showReviewStart(r.params);
    else if (r.view === 'srs-session') await showReviewSession(r.params);
    else if (r.view === 'quiz') await showQuiz(r.params);
    else if (r.view === 'exam') await showExam(r.params);
    else if (r.view === 'exam-result') await showExamResult(r.id);
    else if (r.view === 'chat') await showChat(r.params);
    else if (r.view === 'settings') await showSettings();
    else showHome();
  } catch (e) {
    showError(e);
  }
  renderTree();
  const title = r.view === 'note' && state.note ? state.note.title : '';
  document.title = title ? `${title} | Studiu` : 'Studiu';
}

/* ---------- acțiuni ---------- */

async function createFolder(parent) {
  const name = prompt(parent ? 'Numele subtopicului:' : 'Numele materiei:');
  if (!name || !name.trim()) return;
  try {
    const r = await send('/api/folder', { parent, name: name.trim() });
    expandTo(r.path, true);
    await loadTree();
    location.hash = '#/d/' + enc(r.path);
  } catch (e) { toast(e.message, 'error'); }
}

async function createNote(parent) {
  const name = prompt('Numele notiței (prefixul numeric stabilește ordinea, de exemplu „03 Curs 3 - Bilanțul”):');
  if (!name || !name.trim()) return;
  try {
    const r = await send('/api/notita', { parent, name: name.trim() });
    await loadTree();
    location.hash = '#/e/' + enc(r.path);
  } catch (e) { toast(e.message, 'error'); }
}

async function verifyNote() {
  if (!state.note) return;
  try {
    await send('/api/notita/verificat', { path: state.note.path });
    toast('Notița a fost marcată ca verificată.');
    await loadTree();
    await showNote(state.note.path);
    renderTree();
  } catch (e) { toast(e.message, 'error'); }
}

function currentTarget() {
  const r = parseHash();
  if (r.view === 'note' && state.note) return { path: state.note.path, isNote: true };
  if (r.view === 'dir') return { path: r.path, isNote: false };
  return null;
}

async function renameOrMove(kind) {
  const t = currentTarget();
  if (!t) return;
  const name = t.path.split('/').pop();
  const parent = parentDir(t.path);
  let dest;
  if (kind === 'rename') {
    const nn = prompt('Numele nou:', t.isNote ? name.replace(/\.md$/i, '') : name);
    if (!nn || !nn.trim()) return;
    dest = (parent ? parent + '/' : '') + nn.trim();
  } else {
    const folder = prompt('Mută în folderul (cale relativă la notițe, gol = rădăcina). Linkurile din alte notițe nu se actualizează.', parent);
    if (folder === null) return;
    dest = (folder.trim().replace(/^\/+|\/+$/g, '') ? folder.trim().replace(/^\/+|\/+$/g, '') + '/' : '') + name;
  }
  try {
    const r = await send('/api/notita/mutare', { path: t.path, destinatie: dest });
    await loadTree();
    location.hash = (t.isNote ? '#/n/' : '#/d/') + enc(r.path);
    toast(kind === 'rename' ? 'Redenumit.' : 'Mutat.');
  } catch (e) { toast(e.message, 'error'); }
}

async function trashCurrent() {
  const t = currentTarget();
  if (!t) return;
  if (!confirm(`Muți „${displayName(t.path.split('/').pop())}” în coș? Fișierele ajung în .studiu/cos/ și pot fi recuperate de acolo.`)) return;
  try {
    await send('/api/notita/stergere', { path: t.path });
    await loadTree();
    location.hash = parentDir(t.path) ? '#/d/' + enc(parentDir(t.path)) : '#/';
    toast('Mutat în coș.');
  } catch (e) { toast(e.message, 'error'); }
}

function onMainClick(e) {
  const anchor = e.target.closest('a[data-anchor]');
  if (anchor) {
    e.preventDefault();
    const id = decodeURIComponent(anchor.dataset.anchor);
    const target = document.getElementById(id) || document.getElementsByName(id)[0];
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    return;
  }
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const act = btn.dataset.act;
  btn.closest('details.menu')?.removeAttribute('open');
  if (act === 'new-folder') createFolder(state.context);
  else if (act === 'new-note') createNote(state.context);
  else if (act === 'edit' && state.note) location.hash = '#/e/' + enc(state.note.path);
  else if (act === 'verify') verifyNote();
  else if (act === 'save') saveEdit();
  else if (act === 'close-edit' && state.edit) location.hash = '#/n/' + enc(state.edit.path);
  else if (act === 'rename' || act === 'move') renameOrMove(act);
  else if (act === 'trash') trashCurrent();
}

function onKey(e) {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && state.edit) {
    e.preventDefault();
    saveEdit();
    return;
  }
  if (typing) {
    if (e.key === 'Escape' && document.activeElement.id === 'q') document.activeElement.blur();
    return;
  }
  if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
  const view = parseHash().view;
  if (e.key === '/') { e.preventDefault(); $('#q').focus(); $('#q').select(); }
  else if (e.key.toLowerCase() === 'e' && view === 'note' && state.note) {
    location.hash = '#/e/' + enc(state.note.path);
  }
}

function onEditorKey(e) {
  if (e.target.id !== 'src') return;
  if (e.key === 'Tab' && !e.ctrlKey && !e.altKey) {
    e.preventDefault();
    document.execCommand('insertText', false, '  ');
  } else if (e.key === 'Escape' && state.edit) {
    location.hash = '#/n/' + enc(state.edit.path);
  }
}

/* ---------- pornire ---------- */

async function start() {
  $('#tree').addEventListener('click', (e) => {
    const t = e.target.closest('[data-toggle]');
    if (!t) return;
    const p = t.dataset.toggle;
    state.expanded.has(p) ? state.expanded.delete(p) : state.expanded.add(p);
    store.set('expanded', [...state.expanded]);
    renderTree();
  });
  $('#newRoot').addEventListener('click', () => createFolder(''));
  $('#menuBtn').addEventListener('click', () => document.body.classList.toggle('nav-open'));
  $('#searchForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const q = $('#q').value.trim();
    if (q) location.hash = '#/cauta?q=' + enc(q);
  });
  main().addEventListener('click', onMainClick);
  main().addEventListener('input', (e) => { if (e.target.id === 'src') onEditorInput(); });
  main().addEventListener('keydown', onEditorKey);
  document.addEventListener('keydown', onKey);
  window.addEventListener('hashchange', route);
  window.addEventListener('beforeunload', (e) => { if (state.dirty) { e.preventDefault(); e.returnValue = ''; } });
  window.addEventListener('focus', () => { if (!state.dirty) loadTree().catch(() => {}); });
  window.addEventListener('studiu:tree', () => loadTree().catch(() => {}));

  try {
    await loadTree();
  } catch (e) {
    showError(new Error('Nu pot citi folderul de notițe: ' + e.message));
    return;
  }
  route();
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start);
else start();

export { noteHref };
