// Repetiția: pagina de start (câte carduri azi) și sesiunea cu tastatura (Spațiu, 1–4).
import { $, api, enc, esc, noteHref, plural, richText, scopeSelect, send, setView, state, toast } from './util.js';

export async function showReviewStart(params) {
  state.current = '';
  const scope = params.get('scope') || '';
  const d = await api('/api/repetitie/azi?scope=' + enc(scope));
  const total = d.carduri.length;
  const subjects = Object.entries(d.pe_materii);
  setView(`<section class="sheet">
    <h1>Repetiție</h1>
    <p class="lead">${total ? `Azi ai ${plural(total, 'card', 'carduri')}: ${d.scadente} de repetat și ${d.noi} noi.` : 'Nimic de repetat azi. 🎉'}</p>
    <label class="field small"><span>Materia</span>${scopeSelect('srsScope', scope)}</label>
    ${subjects.length ? `<ul class="topic-list">${subjects.map(([s, v]) => `<li><span class="row-flat"><strong>${esc(s)}</strong><span class="sub">${v.scadente} scadente, ${v.noi} noi</span></span></li>`).join('')}</ul>` : ''}
    <div class="actions">${total ? `<a class="btn primary" href="#/repetitie/sesiune?scope=${enc(scope)}">Începe</a>` : ''}</div>
    <p class="meta">Cardurile noi pe zi: ${d.noi_ramase_azi} rămase azi. Ziua de studiu se termină la 04:00.</p>
  </section>`);
  $('#srsScope').addEventListener('change', (e) => { location.hash = '#/repetitie?scope=' + enc(e.target.value); });
}

export async function showReviewSession(params) {
  state.current = '';
  const scope = params.get('scope') || '';
  const note = params.get('notita') || '';
  const d = await api('/api/repetitie/azi?scope=' + enc(note || scope));
  let queue = d.carduri.filter((c) => !note || c.notita === note);
  if (note && !queue.length) {
    // „Repetă cardurile acestei notițe” funcționează și când nimic nu e scadent: un quiz rapid din ele.
    location.hash = '#/quiz?scope=' + enc(note) + '&numar=10&start=1';
    return;
  }
  const stats = { 1: 0, 2: 0, 3: 0, 4: 0 };
  let i = 0;
  let shown = false;
  let started = performance.now();
  const draw = () => {
    if (i >= queue.length) return finish();
    const c = queue[i];
    shown = false;
    started = performance.now();
    const q = c.tip === 'completare' ? c.intrebare.replace(/\{\{c\d+::(.*?)(?:::(.*?))?\}\}/g, (_m, _a, hint) => `[${hint || '...'}]`) : c.intrebare;
    setView(`<section class="sheet study">
      <div class="study-top"><span class="meta">${i + 1} / ${queue.length}${c.nou ? ' · nou' : ''}</span>
        <a class="meta" href="${noteHref(c.notita, c.sectiune || '')}">${esc(c.notita_titlu || c.notita)}</a></div>
      <div class="flash-q">${richText(q)}</div>
      <div id="answer" hidden>
        <div class="flash-a">${richText(c.tip === 'completare' ? c.raspuns.replace(/\{\{c\d+::(.*?)(?:::.*?)?\}\}/g, '$1') : c.raspuns)}</div>
        ${c.explicatie ? `<p class="card-x">${richText(c.explicatie)}</p>` : ''}
        <p><a href="${noteHref(c.notita, c.sectiune || '')}">vezi secțiunea în notiță</a></p>
        <div class="grades">
          ${[['1', 'Din nou'], ['2', 'Greu'], ['3', 'Bine'], ['4', 'Ușor']].map(([n, label]) => `<button class="btn grade g${n}" data-grade="${n}"><span>${label}</span><small>${esc(c.intervale[n])}</small><kbd>${n}</kbd></button>`).join('')}
        </div>
      </div>
      <div class="actions center" id="showBox"><button class="btn primary" id="show">Arată răspunsul <kbd>Spațiu</kbd></button></div>
    </section>`);
    $('#show').addEventListener('click', show);
    $('#show').focus();
  };
  const show = () => {
    shown = true;
    $('#answer').hidden = false;
    $('#showBox').hidden = true;
    $('.grades button[data-grade="3"]')?.focus();
  };
  const grade = async (n) => {
    if (!shown) return;
    const c = queue[i];
    try {
      await send('/api/repetitie/raspuns', { card: c.id, nota: n, ms: Math.round(performance.now() - started) });
      stats[n] += 1;
      if (n === 1) queue.push({ ...c, intervale: { ...c.intervale } });   // revine la finalul sesiunii
      i += 1;
      draw();
    } catch (e) { toast(e.message, 'error'); }
  };
  const finish = () => {
    const done = stats[1] + stats[2] + stats[3] + stats[4];
    setView(`<section class="sheet">
      <h1>Sesiune terminată</h1>
      <p class="lead">${plural(done, 'răspuns', 'răspunsuri')}: ${stats[4]} ușor, ${stats[3]} bine, ${stats[2]} greu, ${stats[1]} din nou.</p>
      <div class="actions"><a class="btn primary" href="#/repetitie">Înapoi la repetiție</a><a class="btn" href="#/examen">Statistici</a></div>
    </section>`);
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (e) => {
    if (/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === ' ' && !shown) { e.preventDefault(); show(); }
    else if (['1', '2', '3', '4'].includes(e.key)) { e.preventDefault(); grade(Number(e.key)); }
  };
  main().addEventListener('click', onClick);
  function onClick(e) { const b = e.target.closest('[data-grade]'); if (b) grade(Number(b.dataset.grade)); }
  document.addEventListener('keydown', onKey);
  state.cleanup = () => { document.removeEventListener('keydown', onKey); main().removeEventListener('click', onClick); };
  if (!queue.length) {
    setView('<section class="sheet"><h1>Nimic de repetat</h1><p class="lead">Nu ai carduri scadente aici.</p><div class="actions"><a class="btn" href="#/repetitie">Înapoi</a></div></section>');
    return;
  }
  draw();
}

function main() { return $('#main'); }
