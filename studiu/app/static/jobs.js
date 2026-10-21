// Urmărirea sarcinilor de durată prin polling la /api/sarcini (la 1,5 s cât timp sunt active).
import { api, enc, esc, noteHref, send, toast } from './util.js';

const watchers = new Map();     // id sarcină → { done, el }
let timer = null;

const labels = { in_asteptare: 'în așteptare', in_lucru: 'în lucru', gata: 'gata', eroare: 'eroare', anulat: 'anulată' };

export function jobRow(j) {
  const link = j.stare === 'gata' && j.rezultat?.path ? `<a href="${noteHref(j.rezultat.path)}">Deschide notița</a>` : '';
  const active = j.stare === 'in_asteptare' || j.stare === 'in_lucru';
  return `<li class="job state-${esc(j.stare)}" data-job="${esc(j.id)}">
    <div class="job-head"><strong>${esc(j.eticheta || j.tip)}</strong><span class="chip">${esc(labels[j.stare] || j.stare)}</span></div>
    ${active ? `<div class="bar" role="progressbar" aria-valuenow="${j.progres}" aria-valuemin="0" aria-valuemax="100"><span style="width:${j.progres}%"></span></div>` : ''}
    <p class="job-msg">${esc(j.mesaj || '')}</p>
    <div class="actions">${link}
      ${active ? '<button class="link-btn" data-job-act="anulare">Anulează</button>' : ''}
      ${j.stare === 'eroare' || j.stare === 'anulat' ? '<button class="link-btn" data-job-act="reluare">Reia</button>' : ''}
    </div></li>`;
}

export async function jobAction(btn) {
  const id = btn.closest('[data-job]').dataset.job;
  try {
    await send(`/api/sarcini/${enc(id)}/${btn.dataset.jobAct}`, {});
    poll();
  } catch (e) { toast(e.message, 'error'); }
}

export function watchJob(id, done, el = null) {
  watchers.set(id, { done, el });
  poll();
}

export const listeners = new Set();   // funcții chemate cu lista completă a sarcinilor

export async function poll() {
  clearTimeout(timer);
  let d;
  try { d = await api('/api/sarcini'); } catch { timer = setTimeout(poll, 3000); return; }
  const all = [...d.active, ...d.terminate];
  for (const [id, w] of [...watchers]) {
    const j = all.find((x) => x.id === id);
    if (!j) continue;
    if (w.el && document.body.contains(w.el)) w.el.innerHTML = `<ul class="job-list">${jobRow(j)}</ul>`;
    if (j.stare !== 'in_asteptare' && j.stare !== 'in_lucru') {
      watchers.delete(id);
      window.dispatchEvent(new Event('studiu:tree'));
      try { await w.done?.(j); } catch { /* ecranul s-a schimbat */ }
    }
  }
  listeners.forEach((fn) => fn(d));
  if (d.active.length || watchers.size) timer = setTimeout(poll, 1500);
}
