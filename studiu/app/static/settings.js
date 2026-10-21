// Setări: diagnoza (/api/stare), configurația AI, consumul lunii, reconstruirea cache-ului.
import { $, api, enc, esc, send, setView, state, toast } from './util.js';

const money = (v) => (v ? `${v.toFixed(4)} USD` : '0 USD');

export async function showSettings() {
  state.current = '';
  const s = await api('/api/stare');
  const u = s.utilitare;
  const ai = s.ai;
  const c = s.consum;
  const providers = Object.entries(ai.furnizori);
  const usedProviders = new Set([ai.implicit.rezolvat, ...Object.values(ai.sarcini).map((x) => x.rezolvat)].map((r) => r.split(':')[0]));
  setView(`<section class="sheet settings">
    <h1>Setări</h1>
    <p class="meta">Studiu ${esc(s.versiune)} · strat AI ${esc(s.versiune_strat_ai)}</p>
    ${s.avertismente.length ? `<div class="review-banner"><p>${s.avertismente.map(esc).join('<br>')}</p></div>` : ''}

    <h2 class="section">Căi</h2>
    <dl class="kv"><dt>Notițe</dt><dd><code>${esc(s.notite)}</code></dd><dt>Cache</dt><dd><code>${esc(s.date)}</code></dd>
      <dt>Configurație</dt><dd><code>${esc(s.config)}</code></dd></dl>

    <h2 class="section">Utilitare de sistem</h2>
    <p class="meta">Distribuția detectată: <strong>${esc(u.distributie || 'nerecunoscută')}</strong></p>
    <ul class="tools">${Object.entries(u.programe).map(([name, t]) => `<li><span class="${t.disponibil ? 'ok' : 'missing'}">${t.disponibil ? '✓' : '✗'}</span> <code>${esc(name)}</code> <span class="muted">${esc(t.rol)}</span></li>`).join('')}
      <li><span class="${u.faster_whisper ? 'ok' : 'missing'}">${u.faster_whisper ? '✓' : '✗'}</span> <code>faster-whisper</code> <span class="muted">transcriere locală (${esc(s.transcriere.mod)}, model ${esc(s.transcriere.model_local)})${u.faster_whisper ? '' : ' — <code>./studiu.sh --instaleaza-transcriere</code>'}</span></li></ul>
    ${u.comanda_instalare ? `<div class="copy-row"><code id="instCmd">${esc(u.comanda_instalare)}</code><button class="btn" data-copy="instCmd">Copiază</button></div>
      <p class="meta">Sau: <code>./studiu.sh --instaleaza-sistem</code> (cere confirmare înainte de sudo).</p>` : '<p class="meta">Toate utilitarele opționale sunt instalate.</p>'}

    <h2 class="section">AI</h2>
    <p class="meta">Se configurează în <code>${esc(ai.fisier)}</code>, cheile în <code>${esc(ai.fisier_chei)}</code>. Editarea se face în fișier, ca să nu se piardă comentariile.</p>
    ${ai.erori.length ? `<div class="review-banner"><p><strong>Probleme în configurație:</strong><br>${ai.erori.map(esc).join('<br>')}</p></div>` : ''}
    <table class="tbl"><thead><tr><th>Furnizor</th><th>Tip</th><th>Cheie</th><th></th></tr></thead><tbody>
      ${providers.filter(([n]) => usedProviders.has(n) || ai.furnizori[n].cheie_prezenta).map(([name, p]) => `<tr>
        <td><strong>${esc(name)}</strong>${p.local ? ' <span class="chip">local</span>' : ''}${p.gratuit ? ' <span class="chip">gratuit</span>' : ''}<br><small class="muted">${esc(p.base_url)}</small></td>
        <td>${esc(p.tip)}</td>
        <td>${p.cheie_prezenta === null ? 'fără cheie' : p.cheie_prezenta ? `<span class="ok">${esc(p.cheie)} prezentă</span>` : `<span class="missing">${esc(p.cheie)} lipsește</span>`}</td>
        <td class="nowrap"><button class="link-btn" data-test="${esc(name)}">Testează</button> <button class="link-btn" data-models="${esc(name)}">Arată modelele</button></td>
      </tr><tr class="detail" hidden data-detail="${esc(name)}"><td colspan="4"></td></tr>`).join('')}
    </tbody></table>
    <h3 class="sub-h">Sarcini</h3>
    <table class="tbl"><thead><tr><th>Sarcină</th><th>Setare</th><th>Model</th></tr></thead><tbody>
      <tr><td>(implicit)</td><td>${esc(ai.implicit.ref)}</td><td><code>${esc(ai.implicit.rezolvat)}</code></td></tr>
      ${Object.entries(ai.sarcini).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${esc(v.ref)}</td><td><code>${esc(v.rezolvat)}</code></td></tr>`).join('')}
    </tbody></table>
    ${providers.some(([, p]) => p.base_url.includes('googleapis.com') && p.gratuit) ? '<p class="meta">Notă: pe free tier-ul Gemini, datele trimise pot fi folosite de Google pentru îmbunătățirea produselor (cu excepții regionale descrise în termenii lor).</p>' : ''}

    <h2 class="section">Consumul lunii ${esc(c.luna)}</h2>
    <p>${c.apeluri} apeluri · ${(c.intrare + c.iesire).toLocaleString('ro-RO')} tokeni · ${money(c.cost_usd)}${c.buget_lunar_usd ? ` · ${Math.round(c.cost_usd / c.buget_lunar_usd * 100)}% din bugetul de ${c.buget_lunar_usd} USD` : ' · fără buget lunar'}</p>
    ${['aplicatii', 'sarcini', 'modele'].map((g) => Object.keys(c[g]).length ? `<h3 class="sub-h">Pe ${g === 'aplicatii' ? 'aplicații' : g}</h3><table class="tbl"><tbody>${Object.entries(c[g]).map(([k, v]) => `<tr><td>${esc(k)}</td><td>${v.apeluri} apeluri</td><td>${(v.intrare + v.iesire).toLocaleString('ro-RO')} tokeni</td><td>${money(v.cost_usd)}</td></tr>`).join('')}</tbody></table>` : '').join('')}

    <h2 class="section">Întreținere</h2>
    <p class="meta">Cache-ul (index, stările repetițiilor) se reconstruiește din fișiere; nu se pierde nimic.</p>
    <div class="actions"><button class="btn" id="rebuild">Reconstruiește cache-ul</button></div>
  </section>`);

  $('#main').querySelector('.settings').addEventListener('click', async (e) => {
    const copy = e.target.closest('[data-copy]');
    if (copy) {
      try { await navigator.clipboard.writeText($('#' + copy.dataset.copy).textContent); toast('Copiat.'); } catch { toast('Nu pot copia; selectează textul manual.', 'error'); }
      return;
    }
    const test = e.target.closest('[data-test]');
    const mods = e.target.closest('[data-models]');
    if (test || mods) {
      const name = (test || mods).dataset.test || (mods && mods.dataset.models);
      const row = document.querySelector(`[data-detail="${CSS.escape(name)}"]`);
      row.hidden = false;
      const cell = row.firstElementChild;
      cell.innerHTML = '<span class="meta">Se verifică…</span>';
      try {
        if (test) {
          const firstModel = Object.values(ai.sarcini).map((x) => x.rezolvat).concat([ai.implicit.rezolvat]).find((r) => r.startsWith(name + ':'));
          const r = await send('/api/ai/test', { model: firstModel || null });
          cell.innerHTML = `<span class="${r.ok ? 'ok' : 'missing'}">${r.ok ? '✓' : '✗'}</span> ${esc(r.furnizor)}:${esc(r.model)} — ${esc(r.mesaj)} (${r.durata_s} s)${r.note.map((n) => `<br><small class="muted">${esc(n)}</small>`).join('')}`;
        } else {
          const r = await api('/api/ai/modele/' + enc(name));
          const used = new Set(Object.values(ai.sarcini).map((x) => x.rezolvat).concat([ai.implicit.rezolvat]).filter((x) => x.startsWith(name + ':')).map((x) => x.slice(name.length + 1)));
          const missing = [...used].filter((m) => !r.modele.includes(m));
          cell.innerHTML = `${missing.length ? `<p class="missing">Modelul configurat ${missing.map((m) => `«${esc(m)}»`).join(', ')} nu apare în listă.</p>` : ''}
            <div class="model-list">${r.modele.map((m) => `<code class="${used.has(m) ? 'used' : ''}">${esc(m)}</code>`).join(' ')}</div>`;
        }
      } catch (err) { cell.innerHTML = `<span class="missing">✗</span> ${esc(err.message)}`; }
      return;
    }
    if (e.target.closest('#rebuild')) {
      try { await send('/api/cache/reconstruire', {}); toast('Cache-ul a fost reconstruit.'); window.dispatchEvent(new Event('studiu:tree')); } catch (err) { toast(err.message, 'error'); }
    }
  });
}
