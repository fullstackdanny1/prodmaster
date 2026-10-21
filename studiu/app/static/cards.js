// Panoul „Carduri” de pe pagina notiței și secțiunea „Carduri orfane” din De revizuit.
import { api, costText, enc, esc, modelSelect, noteHref, plural, richText, send, toast } from './util.js';
import { watchJob } from './jobs.js';

const stateLabel = { activ: 'activ', suspendat: 'suspendat', orfan: 'orfan' };

function cardRow(c, withNote = false) {
  const variants = c.variante ? `<ol class="variants">${c.variante.map((v, i) => `<li class="${i === c.corect ? 'right' : ''}">${richText(v)}</li>`).join('')}</ol>` : '';
  const link = c.notita ? `<a href="${noteHref(c.notita, c.sectiune || '')}">vezi în notiță</a>` : '';
  return `<li class="card-item state-${esc(c.stare)}" data-card="${esc(c.id)}">
    <div class="card-q">${richText(c.tip === 'completare' ? c.intrebare.replace(/\{\{c\d+::(.*?)(::.*?)?\}\}/g, '[$1]') : c.intrebare)}</div>
    <div class="card-a">${richText(c.raspuns)}</div>
    ${variants}
    ${c.explicatie ? `<p class="card-x">${richText(c.explicatie)}</p>` : ''}
    <div class="card-meta">
      <span class="chip">${c.origine === 'manual' ? 'din notiță' : 'AI'}</span>
      ${c.modificat_manual ? '<span class="chip">editat</span>' : ''}
      ${c.stare !== 'activ' ? `<span class="chip warn">${esc(stateLabel[c.stare] || c.stare)}</span>` : ''}
      ${c.motiv ? `<span class="muted">${esc(c.motiv)}</span>` : ''}
      ${withNote && c.notita_titlu ? `<span class="muted">${esc(c.notita_titlu)}</span>` : ''}
      ${link}
    </div>
    <div class="card-actions">
      ${c.stare === 'orfan' ? `<button class="link-btn" data-card-act="pastreaza">Păstrează</button>
        <button class="link-btn" data-card-act="regenereaza">Regenerează secțiunea</button>` : ''}
      ${c.origine !== 'manual' ? '<button class="link-btn" data-card-act="edit">Editează</button>' : ''}
      ${c.stare === 'suspendat' ? '<button class="link-btn" data-card-act="activ">Reactivează</button>'
        : c.stare === 'activ' ? '<button class="link-btn" data-card-act="suspendat">Suspendă</button>' : ''}
      <button class="link-btn danger" data-card-act="sters">Șterge</button>
    </div>
  </li>`;
}

function editForm(c) {
  const variants = (c.variante || []).join('\n');
  return `<form class="card-edit" data-card="${esc(c.id)}">
    <label class="field"><span>Întrebarea</span><textarea name="intrebare" rows="2">${esc(c.intrebare)}</textarea></label>
    <label class="field"><span>Răspunsul</span><textarea name="raspuns" rows="2">${esc(c.raspuns)}</textarea></label>
    <label class="field"><span>Variante (una pe linie, gol = fără variante)</span><textarea name="variante" rows="4">${esc(variants)}</textarea></label>
    <label class="field small"><span>Varianta corectă (1, 2, …)</span><input name="corect" type="number" min="1" value="${c.corect != null ? c.corect + 1 : 1}"></label>
    <label class="field"><span>Explicație</span><textarea name="explicatie" rows="2">${esc(c.explicatie || '')}</textarea></label>
    <div class="actions"><button class="btn primary" type="submit">Salvează cardul</button><button class="btn" type="button" data-card-act="cancel-edit">Renunță</button></div>
  </form>`;
}

async function cardAction(btn, cards, reload) {
  const li = btn.closest('[data-card]');
  const id = li.dataset.card;
  const c = cards.find((x) => x.id === id);
  const act = btn.dataset.cardAct;
  try {
    if (act === 'edit') { li.innerHTML = editForm(c); return; }
    if (act === 'cancel-edit') { reload(); return; }
    if (act === 'regenereaza') {
      const r = await send('/api/carduri/generare', { path: c.notita, sectiune: c.sectiune || '', confirmat: true });
      toast('Regenerez cardurile secțiunii…');
      watchJob(r.sarcina, () => reload());
      return;
    }
    if (act === 'sters' && !confirm('Ștergi cardul? (Rămâne în fișierul JSON, la „sterse”.)')) return;
    await send(`/api/carduri/${enc(id)}/stare`, { stare: act });
    reload();
  } catch (e) { toast(e.message, 'error'); }
}

async function submitEdit(form, reload) {
  const f = new FormData(form);
  const variante = String(f.get('variante')).split('\n').map((s) => s.trim()).filter(Boolean);
  const body = {
    intrebare: f.get('intrebare'), raspuns: f.get('raspuns'), explicatie: f.get('explicatie'),
    variante: variante.length ? variante : [], corect: variante.length ? Number(f.get('corect')) - 1 : null,
  };
  try {
    await send(`/api/carduri/${enc(form.dataset.card)}`, body, 'PUT');
    toast('Cardul a fost salvat.');
    reload();
  } catch (e) { toast(e.message, 'error'); }
}

function bind(el, getCards, reload) {
  el.addEventListener('click', (e) => {
    const b = e.target.closest('[data-card-act]');
    if (b) { e.preventDefault(); cardAction(b, getCards(), reload); }
  });
  el.addEventListener('submit', (e) => {
    const form = e.target.closest('form.card-edit');
    if (form) { e.preventDefault(); submitEdit(form, reload); }
  });
}

export async function cardsPanel(el, note) {
  let data = null;
  let filter = '';
  const reload = async () => {
    data = await api('/api/carduri?notita=' + enc(note.path));
    draw();
  };
  const draw = () => {
    const cards = data.carduri.filter((c) => !filter || (c.sectiune || '') === filter);
    const active = data.carduri.filter((c) => c.stare === 'activ').length;
    const sections = [...new Set(data.carduri.map((c) => c.sectiune || ''))];
    el.innerHTML = `<section class="cards-panel">
      <div class="head-row">
        <h2 class="section">Carduri <span class="pill soft">${active}</span></h2>
        <div class="actions">
          ${active ? `<a class="btn" href="#/repetitie/sesiune?notita=${enc(note.path)}">Repetă cardurile acestei notițe</a>` : ''}
          ${data.utilizabila ? '<button class="btn primary" data-gen>Generează carduri</button>' : ''}
        </div>
      </div>
      ${data.utilizabila ? '' : '<p class="meta">Cardurile se generează doar din notițe verificate.</p>'}
      <div id="genBox"></div>
      ${data.carduri.length ? `<details class="fold"${data.carduri.length <= 12 ? ' open' : ''}>
        <summary>${plural(data.carduri.length, 'card', 'carduri')}</summary>
        ${sections.length > 1 ? `<label class="field small"><span>Secțiunea</span><select class="select" data-filter>
          <option value="">Toate</option>${sections.map((s) => `<option value="${esc(s)}"${s === filter ? ' selected' : ''}>${esc(s || 'introducere')}</option>`).join('')}
        </select></label>` : ''}
        <ul class="card-list">${cards.map((c) => cardRow({ ...c, notita: note.path })).join('')}</ul>
      </details>` : '<p class="meta">Niciun card încă. Scrie în notiță <code>Q: întrebare</code> urmat de <code>A: răspuns</code> sau <code>{{c1::text ascuns}}</code>, ori generează-le cu AI.</p>'}
    </section>`;
  };
  bind(el, () => data.carduri.map((c) => ({ ...c, notita: note.path })), reload);
  el.addEventListener('change', (e) => { if (e.target.matches('[data-filter]')) { filter = e.target.value; draw(); } });
  el.addEventListener('click', async (e) => {
    if (e.target.closest('[data-gen]')) await showEstimate();
    if (e.target.closest('[data-gen-go]')) await startGeneration();
    if (e.target.closest('[data-gen-cancel]')) el.querySelector('#genBox').innerHTML = '';
  });
  async function showEstimate() {
    const box = el.querySelector('#genBox');
    box.innerHTML = '<p class="meta">Calculez estimarea…</p>';
    try {
      const sel = await modelSelect('genModel', 'carduri');
      const model = () => el.querySelector('#genModel')?.value || null;
      const r = await send('/api/carduri/generare', { path: note.path, confirmat: false, model: null });
      const e = r.estimare;
      box.innerHTML = `<div class="confirm-box">
        ${e.sectiuni ? `<p>${plural(e.sectiuni, 'secțiune nouă sau modificată', 'secțiuni noi sau modificate')} de transformat în carduri.</p>
          <p class="meta" id="genCost">${esc(costText(e))}</p>${sel}
          <div class="actions"><button class="btn primary" data-gen-go>Generează</button><button class="btn" data-gen-cancel>Renunță</button></div>`
        : '<p>Toate secțiunile au deja carduri (sau sunt prea scurte). Pentru o secțiune modificată, folosește „Regenerează” din De revizuit.</p><div class="actions"><button class="btn" data-gen-cancel>Închide</button></div>'}
      </div>`;
      el.querySelector('#genModel')?.addEventListener('change', async () => {
        try {
          const r2 = await send('/api/carduri/generare', { path: note.path, confirmat: false, model: model() });
          el.querySelector('#genCost').textContent = costText(r2.estimare);
        } catch (err) { toast(err.message, 'error'); }
      });
    } catch (err) { box.innerHTML = ''; toast(err.message, 'error'); }
  }
  async function startGeneration() {
    const model = el.querySelector('#genModel')?.value || null;
    const box = el.querySelector('#genBox');
    try {
      const r = await send('/api/carduri/generare', { path: note.path, confirmat: true, model });
      box.innerHTML = '<div class="job-inline" id="genJob"><p class="meta">Pornesc generarea…</p></div>';
      watchJob(r.sarcina, async (job) => {
        if (job.stare === 'gata') toast(`Gata: ${plural(job.rezultat?.carduri_noi || 0, 'card nou', 'carduri noi')}.`);
        else if (job.stare === 'eroare') toast(job.mesaj, 'error');
        await reload();
      }, el.querySelector('#genJob'));
    } catch (err) { toast(err.message, 'error'); }
  }
  await reload();
}

export async function orphansSection(el) {
  let cards = [];
  const reload = async () => {
    const d = await api('/api/revizuit');
    cards = d.carduri_orfane;
    el.innerHTML = cards.length ? `<h2 class="section">Carduri orfane</h2>
      <p class="meta">Secțiunea din care au fost generate s-a schimbat sau a dispărut. Nu apar în repetiții până nu decizi.</p>
      <ul class="card-list">${cards.map((c) => cardRow(c, true)).join('')}</ul>` : '';
  };
  bind(el, () => cards, reload);
  await reload();
}
