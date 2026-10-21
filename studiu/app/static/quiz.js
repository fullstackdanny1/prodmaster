// Quiz (feedback imediat), examen (cronometru, fără feedback până la final) și statistici.
import { $, api, enc, esc, fmtDate, noteHref, plural, richText, scopeSelect, send, setView, state, toast } from './util.js';

const keyTyping = () => /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName);

/* ---------- quiz ---------- */

export async function showQuiz(params) {
  state.current = '';
  const scope = params.get('scope') || '';
  if (params.get('start')) return runQuiz(scope, Number(params.get('numar') || 10), params.get('tip') || 'variante');
  setView(`<section class="sheet">
    <h1>Quiz</h1>
    <p class="lead">Întrebări din cardurile active, cu răspunsul și explicația imediat după fiecare întrebare. Răspunsurile greșite aduc cardul mai repede la repetiție.</p>
    <div class="grid2">
      <label class="field"><span>Folderul (cu subfoldere)</span>${scopeSelect('qzScope', scope)}</label>
      <label class="field"><span>Număr de întrebări</span><select id="qzN" class="select"><option>10</option><option>20</option><option>30</option></select></label>
    </div>
    <fieldset class="field"><legend>Tipul</legend>
      <label class="radio"><input type="radio" name="qzTip" value="variante" checked> variante multiple</label>
      <label class="radio"><input type="radio" name="qzTip" value="scris"> răspuns scris</label>
    </fieldset>
    <div class="actions"><button class="btn primary" id="qzGo">Începe quiz-ul</button></div>
  </section>`);
  $('#qzGo').addEventListener('click', () => runQuiz($('#qzScope').value, Number($('#qzN').value),
    document.querySelector('input[name="qzTip"]:checked').value));
}

function norm(s) {
  return String(s || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

async function runQuiz(scope, n, kind) {
  let questions;
  try { questions = (await send('/api/quiz', { scope, numar: n, tip: kind })).intrebari; } catch (e) {
    setView(`<section class="sheet"><h1>Quiz</h1><p class="lead">${esc(e.message)}</p><div class="actions"><a class="btn" href="#/quiz">Înapoi</a></div></section>`);
    return;
  }
  let i = 0;
  let answered = false;
  let right = 0;
  let started = performance.now();
  const wrongs = [];
  const draw = () => {
    if (i >= questions.length) return done();
    const q = questions[i];
    answered = false;
    started = performance.now();
    setView(`<section class="sheet study">
      <div class="study-top"><span class="meta">${i + 1} / ${questions.length}</span><span class="meta">${right} corecte</span></div>
      <div class="flash-q">${richText(q.intrebare)}</div>
      ${q.tip === 'variante' ? `<ol class="choices">${q.variante.map((v, k) => `<li><button class="choice" data-k="${k}"><kbd>${k + 1}</kbd> ${richText(v)}</button></li>`).join('')}</ol>`
        : `<form id="wForm"><label class="field"><span>Răspunsul tău</span><textarea id="wAns" rows="3"></textarea></label>
           <div class="actions"><button class="btn primary">Verifică <kbd>Enter</kbd></button></div></form>`}
      <div id="fb"></div>
    </section>`);
    if (q.tip === 'scris') {
      $('#wAns').focus();
      $('#wForm').addEventListener('submit', (e) => { e.preventDefault(); checkWritten(); });
      $('#wAns').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); checkWritten(); } });
    }
  };
  const feedback = (ok, q, extra = '') => {
    $('#fb').innerHTML = `<div class="feedback ${ok ? 'ok' : 'bad'}">
      <p><strong>${ok ? 'Corect.' : 'Greșit.'}</strong> Răspunsul: ${richText(q.raspuns)}</p>
      ${q.explicatie ? `<p class="card-x">${richText(q.explicatie)}</p>` : ''}
      ${extra}
      <div class="actions"><a href="${noteHref(q.notita, q.sectiune)}">vezi în notiță</a><button class="btn primary" id="next">Următoarea <kbd>Enter</kbd></button></div>
    </div>`;
    $('#next').addEventListener('click', next);
    $('#next').focus();
  };
  const record = async (q, ok) => {
    try { await send('/api/quiz/raspuns', { card: q.card, corect: ok, ms: Math.round(performance.now() - started), mod: 'quiz' }); } catch (e) { toast(e.message, 'error'); }
  };
  const choose = (k) => {
    const q = questions[i];
    if (answered || q.tip !== 'variante' || k >= q.variante.length) return;
    answered = true;
    const ok = k === q.corect;
    right += ok;
    if (!ok) wrongs.push(q);
    document.querySelectorAll('.choice').forEach((b) => {
      const bk = Number(b.dataset.k);
      b.disabled = true;
      if (bk === q.corect) b.classList.add('right');
      if (bk === k && !ok) b.classList.add('wrong');
    });
    record(q, ok);
    feedback(ok, q);
  };
  const checkWritten = () => {
    const q = questions[i];
    if (answered) return next();
    answered = true;
    const given = $('#wAns').value;
    const auto = norm(given) && norm(given) === norm(q.raspuns);
    $('#fb').innerHTML = `<div class="feedback"><p>Răspunsul corect: ${richText(q.raspuns)}</p>
      ${q.explicatie ? `<p class="card-x">${richText(q.explicatie)}</p>` : ''}
      <p class="meta">${auto ? 'Răspunsul tău se potrivește.' : 'Compară cu răspunsul tău și alege:'}</p>
      <div class="actions"><button class="btn primary" data-self="1">Am știut</button><button class="btn" data-self="0">N-am știut</button>
      <a href="${noteHref(q.notita, q.sectiune)}">vezi în notiță</a></div></div>`;
    $('#fb').querySelectorAll('[data-self]').forEach((b) => b.addEventListener('click', () => {
      const ok = b.dataset.self === '1';
      right += ok;
      if (!ok) wrongs.push(q);
      record(q, ok);
      next();
    }));
    $(auto ? '[data-self="1"]' : '[data-self="0"]', $('#fb')).focus();
  };
  const next = () => { i += 1; draw(); };
  const done = () => {
    document.removeEventListener('keydown', onKey);
    setView(`<section class="sheet">
      <h1>Rezultat: ${right} din ${questions.length}</h1>
      ${wrongs.length ? `<h2 class="section">De recitit</h2><ul class="note-list">${wrongs.map((q) => `<li><a class="row" href="${noteHref(q.notita, q.sectiune)}"><span class="stack"><span>${richText(q.intrebare)}</span><span class="path">${esc(q.notita_titlu || q.notita)}</span></span></a></li>`).join('')}</ul>` : '<p class="lead">Toate corecte.</p>'}
      <div class="actions"><a class="btn primary" href="#/quiz?scope=${enc(scope)}">Alt quiz</a></div>
    </section>`);
  };
  const onKey = (e) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return;
    if (keyTyping() && e.target.id !== 'wAns') return;
    const q = questions[i];
    if (!q) return;
    if (/^[1-9]$/.test(e.key) && q.tip === 'variante' && !keyTyping()) { e.preventDefault(); choose(Number(e.key) - 1); }
    else if (e.key === 'Enter' && answered && q.tip === 'variante') { e.preventDefault(); next(); }
  };
  $('#main').addEventListener('click', onClick);
  function onClick(e) { const b = e.target.closest('.choice'); if (b) choose(Number(b.dataset.k)); }
  document.addEventListener('keydown', onKey);
  state.cleanup = () => { document.removeEventListener('keydown', onKey); $('#main').removeEventListener('click', onClick); };
  draw();
}

/* ---------- examen ---------- */

export async function showExam(params) {
  state.current = '';
  const scope = params.get('scope') || '';
  const [hist, stats] = await Promise.all([api('/api/examene?scope=' + enc(scope)), api('/api/statistici?scope=' + enc(scope))]);
  setView(`<section class="sheet">
    <h1>Examen</h1>
    <p class="lead">Simulare cu timp limită, fără feedback până la final. La expirarea timpului, examenul se trimite singur.</p>
    <div class="grid3">
      <label class="field"><span>Folderul</span>${scopeSelect('exScope', scope)}</label>
      <label class="field"><span>Întrebări</span><input id="exN" type="number" min="5" max="100" value="20"></label>
      <label class="field"><span>Minute</span><input id="exMin" type="number" min="1" max="600" value="30"></label>
    </div>
    <div class="actions"><button class="btn primary" id="exGo">Începe examenul</button></div>
    <h2 class="section">Istoric</h2>
    ${hist.examene.length ? scoreChart(hist.examene) + `<ul class="note-list">${hist.examene.slice().reverse().map((x) => `<li><a class="row" href="#/examen/${enc(x.id)}"><span class="stack"><span class="title">${x.corecte} / ${x.total} (${x.procent}%)</span><span class="path">${esc(fmtDate(x.inceput))}${x.scop ? ' · ' + esc(x.scop) : ''}</span></span></a></li>`).join('')}</ul>` : '<p class="meta">Niciun examen încă.</p>'}
    ${statsHtml(stats)}
  </section>`);
  $('#exScope').addEventListener('change', (e) => { location.hash = '#/examen?scope=' + enc(e.target.value); });
  $('#exGo').addEventListener('click', () => runExam($('#exScope').value, Number($('#exN').value), Number($('#exMin').value)));
}

function scoreChart(items) {
  const w = 600, h = 160, pad = 28;
  const pts = items.map((x, k) => [pad + (items.length === 1 ? (w - 2 * pad) / 2 : k * (w - 2 * pad) / (items.length - 1)), h - pad - x.procent / 100 * (h - 2 * pad), x]);
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const grid = [0, 50, 100].map((p) => { const y = h - pad - p / 100 * (h - 2 * pad); return `<line x1="${pad}" x2="${w - pad}" y1="${y}" y2="${y}" class="grid-line"/><text x="4" y="${y + 4}" class="axis">${p}%</text>`; }).join('');
  return `<figure class="chart"><svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Scorurile examenelor în timp">${grid}
    <polyline points="${line}" class="score-line"/>${pts.map(([x, y, it]) => `<circle cx="${x}" cy="${y}" r="4" class="score-dot"><title>${esc(fmtDate(it.inceput))}: ${it.procent}%</title></circle>`).join('')}</svg></figure>`;
}

function statsHtml(s) {
  const max = Math.max(1, ...s.pe_zile.map((d) => d.raspunsuri));
  const bars = s.pe_zile.map((d, k) => { const bh = Math.round(d.raspunsuri / max * 60); return `<rect x="${k * 6.6}" y="${64 - bh}" width="5" height="${Math.max(bh, d.raspunsuri ? 2 : 0)}" class="bar-day"><title>${d.zi}: ${d.raspunsuri}</title></rect>`; }).join('');
  const total = s.pe_zile.reduce((a, d) => a + d.raspunsuri, 0);
  return `<h2 class="section">Statistici</h2>
    <p class="meta">${plural(total, 'răspuns', 'răspunsuri')} în ultimele 90 de zile · ${s.carduri.active} carduri active${s.carduri.orfane ? `, ${s.carduri.orfane} orfane` : ''}</p>
    <figure class="chart"><svg viewBox="0 0 594 66" role="img" aria-label="Repetiții pe zi, ultimele 90 de zile">${bars}</svg></figure>
    <h3 class="sub-h">Prognoza (7 zile)</h3>
    <div class="forecast">${s.prognoza.map((d) => `<span><strong>${d.carduri}</strong><small>${new Date(d.zi).toLocaleDateString('ro-RO', { weekday: 'short' })}</small></span>`).join('')}</div>
    ${s.pe_materii.length ? `<h3 class="sub-h">Rata de reușită pe materii</h3><ul class="rates">${s.pe_materii.map((m) => rateRow(m.materie, m)).join('')}</ul>` : ''}
    ${s.topicuri_slabe.length ? `<h3 class="sub-h">Topicuri slabe</h3><ul class="rates">${s.topicuri_slabe.map((t) => rateRow(`<a href="${noteHref(t.notita, t.sectiune)}">${esc(t.titlu)}${t.titlu_sectiune ? ' · ' + esc(t.titlu_sectiune) : ''}</a>`, t, true)).join('')}</ul>` : ''}`;
}

function rateRow(label, v, raw = false) {
  return `<li><span>${raw ? label : esc(label)}</span><span class="rate"><span class="rate-bar"><span style="width:${v.procent}%"></span></span>${v.procent}% <small>(${v.corecte}/${v.total})</small></span></li>`;
}

async function runExam(scope, n, minutes) {
  let ex;
  try { ex = await send('/api/examen', { scope, numar: n, minute: minutes }); } catch (e) { toast(e.message, 'error'); return; }
  const answers = ex.intrebari.map((q) => ({ card: q.card, ales: null, ms: 0 }));
  const deadline = Date.now() + minutes * 60000;
  let i = 0;
  let shownAt = performance.now();
  let submitted = false;
  const tick = () => {
    const left = Math.max(0, deadline - Date.now());
    const el = $('#timer');
    if (el) {
      el.textContent = `${String(Math.floor(left / 60000)).padStart(2, '0')}:${String(Math.floor(left / 1000) % 60).padStart(2, '0')}`;
      el.classList.toggle('urgent', left < 60000);
    }
    if (left <= 0) submit(true);
  };
  const track = () => { answers[i].ms += Math.round(performance.now() - shownAt); shownAt = performance.now(); };
  const draw = () => {
    const q = ex.intrebari[i];
    setView(`<section class="sheet study">
      <div class="study-top"><span class="meta">Întrebarea ${i + 1} din ${ex.intrebari.length}</span><span id="timer" class="timer" aria-live="off"></span></div>
      <div class="flash-q">${richText(q.intrebare)}</div>
      ${q.variante ? `<ol class="choices">${q.variante.map((v, k) => `<li><button class="choice${answers[i].ales === k ? ' picked' : ''}" data-k="${k}"><kbd>${k + 1}</kbd> ${richText(v)}</button></li>`).join('')}</ol>`
        : '<p class="meta">(Întrebare fără variante: nu se punctează în examen.)</p>'}
      <nav class="exam-nav" aria-label="Întrebări">${ex.intrebari.map((_q, k) => `<button class="qdot${k === i ? ' on' : ''}${answers[k].ales !== null ? ' done' : ''}" data-go="${k}" aria-label="Întrebarea ${k + 1}">${k + 1}</button>`).join('')}</nav>
      <div class="actions"><button class="btn" id="prev" ${i === 0 ? 'disabled' : ''}>Înapoi</button><button class="btn" id="nextQ" ${i === ex.intrebari.length - 1 ? 'disabled' : ''}>Înainte</button>
        <button class="btn primary" id="submit">Trimite examenul</button></div>
    </section>`);
    tick();
  };
  const go = (k) => { if (k < 0 || k >= ex.intrebari.length) return; track(); i = k; draw(); };
  const onClick = (e) => {
    const c = e.target.closest('.choice');
    if (c) { answers[i].ales = Number(c.dataset.k); draw(); return; }
    const d = e.target.closest('[data-go]');
    if (d) { go(Number(d.dataset.go)); return; }
    if (e.target.closest('#prev')) go(i - 1);
    else if (e.target.closest('#nextQ')) go(i + 1);
    else if (e.target.closest('#submit')) {
      const missing = answers.filter((a) => a.ales === null).length;
      if (!missing || confirm(`Ai ${plural(missing, 'întrebare fără răspuns', 'întrebări fără răspuns')}. Trimiți?`)) submit(false);
    }
  };
  const onKey = (e) => {
    if (keyTyping() || e.ctrlKey || e.metaKey || e.altKey) return;
    const q = ex.intrebari[i];
    if (/^[1-9]$/.test(e.key) && q.variante && Number(e.key) <= q.variante.length) { answers[i].ales = Number(e.key) - 1; draw(); }
    else if (e.key === 'ArrowRight' || e.key === 'Enter') go(i + 1);
    else if (e.key === 'ArrowLeft') go(i - 1);
  };
  const timer = setInterval(tick, 500);
  const stop = () => { clearInterval(timer); document.removeEventListener('keydown', onKey); $('#main').removeEventListener('click', onClick); };
  async function submit(auto) {
    if (submitted) return;
    submitted = true;
    track();
    stop();
    state.cleanup = null;
    try {
      await send(`/api/examen/${enc(ex.id)}/final`, { raspunsuri: answers });
      if (auto) toast('Timpul a expirat: examenul a fost trimis automat.');
      location.hash = '#/examen/' + enc(ex.id);
    } catch (e) { toast(e.message, 'error'); }
  }
  $('#main').addEventListener('click', onClick);
  document.addEventListener('keydown', onKey);
  const examHash = location.hash;
  const guard = () => {
    if (submitted) return true;
    if (!confirm('Examenul e în desfășurare. Îl părăsești? Răspunsurile nu se salvează.')) {
      history.replaceState(null, '', examHash);   // nu declanșează hashchange
      state.cleanup = guard;
      return false;
    }
    stop();
    return true;
  };
  state.cleanup = guard;
  draw();
}

export async function showExamResult(id) {
  state.current = '';
  const r = await api('/api/examen/' + enc(id));
  const sc = r.scor || { corecte: 0, total: 0 };
  const pct = sc.total ? Math.round(sc.corecte / sc.total * 100) : 0;
  const weakest = r.pe_subtopicuri[0];
  setView(`<section class="sheet">
    <nav class="crumbs"><a href="#/examen${r.scop ? '?scope=' + enc(r.scop) : ''}">Examen</a><span class="sep">/</span><strong>${esc(fmtDate(r.inceput))}</strong></nav>
    <h1>Scor: ${sc.corecte} din ${sc.total} (${pct}%)</h1>
    ${weakest && weakest.procent < 100 ? `<p class="lead">Cel mai slab: <strong>${esc(weakest.subtopic)}</strong> (${weakest.procent}%).${weakest.sectiuni.length ? ' Recitește: ' + weakest.sectiuni.map((s) => `<a href="${noteHref(s.notita, s.sectiune)}">${esc(s.titlu)}${s.titlu_sectiune ? ' · ' + esc(s.titlu_sectiune) : ''}</a>`).join(', ') : ''}</p>` : ''}
    <h2 class="section">Pe subtopicuri</h2>
    <ul class="rates">${r.pe_subtopicuri.map((t) => rateRow(t.subtopic, t)).join('')}</ul>
    <h2 class="section">Greșeli</h2>
    ${r.greseli.length ? `<ul class="card-list">${r.greseli.map((g) => `<li class="card-item">
      <div class="card-q">${richText(g.intrebare)}</div>
      <p>${g.ales != null ? `Ai ales: <span class="wrong-text">${richText(g.ales)}</span><br>` : 'Fără răspuns.<br>'}Corect: <strong>${richText(g.raspuns)}</strong></p>
      ${g.explicatie ? `<p class="card-x">${richText(g.explicatie)}</p>` : ''}
      <a href="${noteHref(g.notita, g.sectiune)}">vezi secțiunea</a></li>`).join('')}</ul>` : '<p class="lead">Nicio greșeală.</p>'}
    <div class="actions"><a class="btn primary" href="#/examen${r.scop ? '?scope=' + enc(r.scop) : ''}">Alt examen</a></div>
  </section>`);
}
