// Ecranul Import: fișier (PDF, audio, video) sau link → estimare → confirmare → sarcină.
import { $, api, costText, esc, modelSelect, scopeSelect, send, setView, state, toast } from './util.js';
import { jobAction, jobRow, listeners, poll } from './jobs.js';

let chosen = null;     // fișierul ales

export async function showImport() {
  state.current = '';
  chosen = null;
  const models = await modelSelect('impModel', 'notite');
  setView(`<section class="sheet">
    <h1>Import</h1>
    <p class="lead">Un PDF de curs, o înregistrare audio/video sau un articol web devine o notiță Markdown. Notițele scrise de AI ajung în „De revizuit”; articolele web se importă fără AI.</p>
    <div class="drop" id="drop" tabindex="0" role="button" aria-label="Alege sau trage un fișier">
      <p><strong>Trage aici un fișier</strong> sau <button class="link-btn" id="pick" type="button">alege unul</button></p>
      <p class="meta">PDF, MP3, M4A, WAV, OGG, MP4, MKV, WEBM…</p>
      <p id="fileName" class="file-name"></p>
      <input type="file" id="file" hidden accept=".pdf,audio/*,video/*,.mkv">
    </div>
    <label class="field"><span>sau un link spre un articol</span><input id="url" type="url" placeholder="https://…" autocomplete="off"></label>
    <div class="grid2">
      <label class="field"><span>Folderul destinație</span>${scopeSelect('impFolder', state.context, '(rădăcina notițelor)')}</label>
      <label class="field"><span>Folder nou în el (opțional)</span><input id="impNewFolder" placeholder="de exemplu Curs 5"></label>
    </div>
    <label class="field"><span>Numele notiței (opțional)</span><input id="impName" placeholder="derivat din fișier sau din titlu"></label>
    ${models}
    <div class="actions"><button class="btn primary" id="impEstimate">Continuă</button></div>
    <div id="impConfirm"></div>
    <h2 class="section">Sarcini</h2>
    <ul class="job-list" id="jobList"><li class="meta">Se încarcă…</li></ul>
  </section>`);

  const drop = $('#drop');
  const fileInput = $('#file');
  const setFile = (f) => { chosen = f; $('#fileName').textContent = f ? `${f.name} (${(f.size / 1048576).toFixed(1)} MB)` : ''; $('#impConfirm').innerHTML = ''; };
  $('#pick').addEventListener('click', () => fileInput.click());
  drop.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
  fileInput.addEventListener('change', () => setFile(fileInput.files[0] || null));
  ['dragenter', 'dragover'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', (e) => setFile(e.dataTransfer.files[0] || null));
  $('#impEstimate').addEventListener('click', estimate);
  $('#jobList').addEventListener('click', (e) => { const b = e.target.closest('[data-job-act]'); if (b) jobAction(b); });

  const draw = (d) => {
    const list = $('#jobList');
    if (!list) { listeners.delete(draw); return; }
    const all = [...d.active, ...d.terminate];
    list.innerHTML = all.length ? all.map(jobRow).join('') : '<li class="meta">Nicio sarcină încă.</li>';
  };
  listeners.add(draw);
  state.cleanup = () => { listeners.delete(draw); };
  poll();
}

function formData() {
  const fd = new FormData();
  const url = $('#url').value.trim();
  if (chosen) fd.append('fisier', chosen);
  else if (url) fd.append('url', url);
  const model = $('#impModel')?.value;
  if (model) fd.append('model', model);
  return fd;
}

async function ensureFolder() {
  const base = $('#impFolder').value;
  const extra = $('#impNewFolder').value.trim();
  if (!extra) return base;
  try {
    const r = await send('/api/folder', { parent: base, name: extra });
    window.dispatchEvent(new Event('studiu:tree'));
    return r.path;
  } catch (e) {
    if (/există deja/.test(e.message)) return (base ? base + '/' : '') + extra;
    throw e;
  }
}

async function estimate() {
  const box = $('#impConfirm');
  if (!chosen && !$('#url').value.trim()) { toast('Alege un fișier sau scrie un link.', 'error'); return; }
  box.innerHTML = '<p class="meta">Calculez estimarea…</p>';
  try {
    const e = await api('/api/import/estimare', { method: 'POST', body: formData() });
    const what = e.tip === 'web' ? 'Articol web: se extrage textul principal, fără AI.'
      : e.tip === 'pdf' ? `PDF cu ${e.pagini} pagini${e.scanat ? ' (scanat)' : ''}, ${e.bucati} bucăți de text.`
        : `Înregistrare${e.durata_s ? ` de ${Math.round(e.durata_s / 60)} min` : ''}: transcriere, apoi ${e.bucati} bucăți de text.`;
    box.innerHTML = `<div class="confirm-box">
      <p>${esc(what)}</p>
      ${e.tip !== 'web' ? `<p class="meta">${esc(costText(e))}</p>` : ''}
      ${e.avertisment ? `<p class="warn-line">${esc(e.avertisment)}</p>` : ''}
      <div class="actions"><button class="btn primary" id="impGo">Pornește importul</button><button class="btn" id="impCancel">Renunță</button></div>
    </div>`;
    $('#impCancel').addEventListener('click', () => { box.innerHTML = ''; });
    $('#impGo').addEventListener('click', start);
  } catch (err) { box.innerHTML = ''; toast(err.message, 'error'); }
}

async function start() {
  try {
    const fd = formData();
    fd.append('folder', await ensureFolder());
    const name = $('#impName').value.trim();
    if (name) fd.append('nume', name);
    await api('/api/import', { method: 'POST', body: fd });
    toast('Importul a pornit. Poți folosi aplicația între timp.');
    $('#impConfirm').innerHTML = '';
    chosen = null;
    $('#fileName').textContent = '';
    $('#url').value = '';
    poll();
  } catch (e) { toast(e.message, 'error'); }
}
