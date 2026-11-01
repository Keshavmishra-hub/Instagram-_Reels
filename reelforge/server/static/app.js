/* ReelForge Studio - single-page UI (vanilla JS). Every dynamic string goes through esc(). */
'use strict';

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, (c) => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const api = {
  async req(method, url, body, isForm) {
    const opts = {method, headers: {}};
    if (body !== undefined) {
      if (isForm) opts.body = body;
      else { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    }
    const r = await fetch(url, opts);
    const text = await r.text();
    let data; try { data = text ? JSON.parse(text) : {}; } catch { data = {detail: text}; }
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
    return data;
  },
  get: (u) => api.req('GET', u), post: (u, b) => api.req('POST', u, b ?? {}), put: (u, b) => api.req('PUT', u, b),
  patch: (u, b) => api.req('PATCH', u, b), upload: (u, form) => api.req('POST', u, form, true),
};

let META = null;
let STATE = null;
let PID = null;
let TAB = 'research';
let POLL = null;
const TABS = [['research', 'Research'], ['script', 'Script'], ['storyboard', 'Storyboard'], ['produce', 'Produce'], ['publish', 'Publish']];
const STATUS_OF_TAB = {research: 'research', script: 'script', storyboard: 'storyboard', produce: 'render', publish: 'qc'};

function toast(msg, bad = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.className = 'toast' + (bad ? ' bad' : '');
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add('hidden'), 6000);
}
const badge = (s, label) => `<span class="badge b-${esc(s)}">${esc(label ?? String(s).replace('_', ' '))}</span>`;
const dot = (s) => `<span class="dot ${esc(s || 'pending')}"></span>`;

/* ----------------------------------------------------------------------------- boot + routing */
async function init() {
  META = await api.get('/api/meta');
  renderCaps();
  await loadProjects();
  window.addEventListener('hashchange', route);
  route();
}

function renderCaps() {
  const c = META.capabilities;
  const caps = [
    ['Claude API', c.llm.configured], ['Pexels', c.stock.pexels], ['Pixabay', c.stock.pixabay], ['Wikimedia', c.stock.wikimedia],
    ['Kokoro TTS', c.tts.kokoro.model], ['ElevenLabs', c.tts.elevenlabs], ['Azure TTS', c.tts.azure], ['OpenAI TTS', c.tts.openai],
    ['ASR QC', !!c.asr.engine], ['Renderer', c.renderer.installed],
  ];
  $('#caps').innerHTML = caps.map(([n, on]) => `<span class="cap ${on ? 'on' : ''}" title="${on ? 'configured' : 'not configured'}">${on ? '✓' : '○'} ${esc(n)}</span>`).join('');
}

async function loadProjects() {
  const list = await api.get('/api/projects');
  $('#projects').innerHTML = list.length ? list.map((p) => `
    <a href="#/p/${esc(p.id)}" class="${p.id === PID ? 'active' : ''}">
      <span class="pl-topic">${esc(p.topic)}</span>
      <span class="pl-meta">${p.complete ? '✓ complete' : esc(Object.entries(p.stages).filter(([, s]) => s === 'done').length + '/8 stages')}</span>
    </a>`).join('') : '<div class="muted small">No projects yet.</div>';
}

async function route() {
  const h = location.hash || '#/new';
  clearInterval(POLL);
  if (h.startsWith('#/p/')) {
    const [, , pid, tab] = h.split('/');
    PID = pid;
    TAB = tab || TAB || 'research';
    await refresh();
  } else {
    PID = null;
    renderNew();
  }
  loadProjects();
}

async function refresh() {
  try {
    STATE = await api.get(`/api/projects/${PID}`);
  } catch (e) {
    $('#main').innerHTML = `<div class="empty">${esc(e.message)}</div>`;
    return;
  }
  renderProject();
  const job = STATE.job;
  if (job && (job.status === 'running' || job.status === 'queued')) watchJob(job.id, true);
}

/* ----------------------------------------------------------------------------- new project */
function renderNew() {
  const langs = META.languages.map((l) => `<option value="${esc(l.code)}">${esc(l.name)}${l.kokoro ? '' : ' (cloud voice)'}</option>`).join('');
  const brands = META.brands.map((b) => `<option value="${esc(b.key)}">${esc(b.name)}</option>`).join('');
  const styles = META.styles.map((s, i) => `<div class="style-card ${i === 0 ? 'on' : ''}" data-style="${esc(s.key)}"><b>${esc(s.name)}</b><span>${esc(s.description)}</span></div>`).join('');
  const moods = META.music_moods.map((m) => `<option value="${m}">${m}</option>`).join('');
  $('#main').innerHTML = `
    <h1>New reel</h1>
    <p class="muted">Topic → research → fact verification → script → storyboard → voice-over → visuals → subtitles → edit → quality check → Instagram-ready reel.</p>
    <div class="card">
      <label>Topic</label>
      <input id="f-topic" type="text" placeholder="e.g. How Operation Flood made India the world's largest milk producer" />
      <div class="grid3">
        <div><label>Language</label><select id="f-lang">${langs}</select></div>
        <div><label>Duration</label><div class="chips" id="f-dur">${[30, 45, 60, 75, 90].map((d) => `<span class="chip ${d === 45 ? 'on' : ''}" data-v="${d}">${d}s</span>`).join('')}</div></div>
        <div><label>Brand kit</label><select id="f-brand">${brands}</select></div>
      </div>
      <label>Storytelling style</label>
      <div class="style-grid" id="f-style">${styles}</div>
      <div class="grid3">
        <div><label>Voice provider</label><select id="f-tts"></select></div>
        <div><label>Voice</label><select id="f-voice"></select></div>
        <div><label>Pace: <span id="f-speed-v">1.00</span>×</label><input id="f-speed" type="range" min="0.85" max="1.15" step="0.01" value="1" style="width:100%"></div>
      </div>
      <div class="grid3">
        <div><label>Tone</label><select id="f-tone"><option>auto</option><option>calm</option><option>warm</option><option>energetic</option><option>serious</option></select></div>
        <div><label>Music mood</label><select id="f-music">${moods}</select></div>
        <div><label>Audience (optional)</label><input id="f-aud" type="text" placeholder="e.g. Indian farmers and agri students" /></div>
      </div>
      <label>Angle / instructions (optional)</label>
      <input id="f-angle" type="text" placeholder="e.g. focus on what it means for small dairy farmers" />
      <div class="row" style="margin-top:16px"><button class="btn btn-primary" id="f-create">Create project</button></div>
    </div>`;
  const dur = $('#f-dur');
  dur.onclick = (e) => { const c = e.target.closest('.chip'); if (!c) return; dur.querySelectorAll('.chip').forEach((x) => x.classList.remove('on')); c.classList.add('on'); };
  $('#f-style').onclick = (e) => { const c = e.target.closest('.style-card'); if (!c) return; $('#f-style').querySelectorAll('.style-card').forEach((x) => x.classList.remove('on')); c.classList.add('on'); };
  $('#f-speed').oninput = (e) => ($('#f-speed-v').textContent = Number(e.target.value).toFixed(2));
  const fillVoices = () => {
    const lang = META.languages.find((l) => l.code === $('#f-lang').value);
    const caps = META.capabilities.tts;
    const providers = [];
    if (lang.kokoro) providers.push(['kokoro', 'Kokoro (local, free)']);
    providers.push(['azure', `Azure Speech${caps.azure ? '' : ' (needs key)'}`], ['elevenlabs', `ElevenLabs${caps.elevenlabs ? '' : ' (needs key)'}`], ['openai', `OpenAI${caps.openai ? '' : ' (needs key)'}`]);
    $('#f-tts').innerHTML = providers.map(([v, n]) => `<option value="${v}">${esc(n)}</option>`).join('');
    fillVoiceList();
  };
  const fillVoiceList = () => {
    const lang = META.languages.find((l) => l.code === $('#f-lang').value);
    const p = $('#f-tts').value;
    let opts = [];
    if (p === 'kokoro') opts = lang.kokoro_voices.map((v) => [v, META.kokoro_voices[v] || v]);
    else if (p === 'azure') opts = lang.azure_voices.map((v) => [v, v]);
    else if (p === 'openai') opts = META.openai_voices.map((v) => [v, v]);
    else opts = [['', 'Default (George) - or paste a voice ID in settings']];
    $('#f-voice').innerHTML = opts.map(([v, n]) => `<option value="${esc(v)}">${esc(n)}</option>`).join('');
  };
  $('#f-lang').onchange = fillVoices;
  $('#f-tts').onchange = fillVoiceList;
  fillVoices();
  $('#f-create').onclick = async () => {
    const body = {
      topic: $('#f-topic').value.trim(), language: $('#f-lang').value, duration: Number($('#f-dur .chip.on').dataset.v),
      style: $('#f-style .style-card.on').dataset.style, brand: $('#f-brand').value, music_mood: $('#f-music').value,
      audience: $('#f-aud').value, angle: $('#f-angle').value,
      narration: {provider: $('#f-tts').value, voice: $('#f-voice').value, speed: Number($('#f-speed').value), tone: $('#f-tone').value},
    };
    if (body.topic.length < 3) return toast('Enter a topic', true);
    try {
      const r = await api.post('/api/projects', body);
      location.hash = `#/p/${r.id}/research`;
    } catch (e) { toast(e.message, true); }
  };
}

/* ----------------------------------------------------------------------------- project shell */
function renderProject() {
  const p = STATE.project;
  const st = p.stages;
  const head = `
    <div class="row spread">
      <div>
        <h1>${esc(p.settings.topic)}</h1>
        <div class="muted small">${esc(p.settings.style)} · ${esc(p.settings.language)} · ${p.settings.duration}s · voice ${esc(p.settings.narration.provider)}/${esc(p.settings.narration.voice)} · ${esc(p.id)}</div>
      </div>
      <div>${p.complete ? badge('pass', '✓ COMPLETE') : (STATE.qc ? badge('fail', 'NOT READY') : badge('info', 'in progress'))}</div>
    </div>
    <div class="steps">${TABS.map(([k, n]) => `<div class="step ${TAB === k ? 'active' : ''}" data-tab="${k}">${dot(st[STATUS_OF_TAB[k]]?.status)} ${n}</div>`).join('')}</div>
    <div id="jobbox" class="card hidden"><div class="row spread"><b id="job-title"></b><span id="job-status" class="muted small"></span></div>
      <div class="progress" style="margin:10px 0"><div id="job-bar"></div></div><div id="job-log" class="console"></div></div>
    <div id="tab"></div>`;
  $('#main').innerHTML = head;
  $('#main').querySelectorAll('.step').forEach((el) => (el.onclick = () => { location.hash = `#/p/${PID}/${el.dataset.tab}`; }));
  ({research: tabResearch, script: tabScript, storyboard: tabStoryboard, produce: tabProduce, publish: tabPublish})[TAB]();
}

async function startJob(url, body) {
  try {
    const r = await api.post(url, body);
    watchJob(r.job);
  } catch (e) { toast(e.message, true); }
}

function watchJob(jid, quiet) {
  const box = $('#jobbox');
  if (!box) return;
  box.classList.remove('hidden');
  clearInterval(POLL);
  const tick = async () => {
    let j;
    try { j = await api.get(`/api/jobs/${jid}`); } catch { clearInterval(POLL); return; }
    $('#job-title').textContent = `Running: ${j.stage}`;
    $('#job-status').textContent = j.status + (j.error ? ` - ${j.error}` : '');
    $('#job-bar').style.width = `${Math.round((j.progress || 0) * 100)}%`;
    const log = $('#job-log');
    log.textContent = j.logs.join('\n');
    log.scrollTop = log.scrollHeight;
    if (!['running', 'queued'].includes(j.status)) {
      clearInterval(POLL);
      if (j.status === 'done') toast(`${j.stage}: done`);
      else toast(`${j.stage}: ${j.error || j.status}`, true);
      const keepLog = j.logs.slice();
      await refresh();
      const b = $('#jobbox');
      if (b) { b.classList.remove('hidden'); $('#job-title').textContent = `Last job: ${j.stage}`; $('#job-status').textContent = j.status + (j.error ? ` - ${j.error}` : ''); $('#job-bar').style.width = j.status === 'done' ? '100%' : `${Math.round((j.progress || 0) * 100)}%`; $('#job-log').textContent = keepLog.join('\n'); }
      loadProjects();
    }
  };
  tick();
  POLL = setInterval(tick, 1200);
  if (!quiet) box.scrollIntoView({behavior: 'smooth', block: 'nearest'});
}

const llm = () => META.capabilities.llm.configured;
const ccHint = (cmd, what) => `<div class="hint">No Claude API key configured. Either add <code>ANTHROPIC_API_KEY</code> to <code>.env</code>, or open <b>Claude Code</b> in this folder and run <code>${esc(cmd)} ${esc(PID)}</code> - it will ${esc(what)} and the results appear here.</div>`;

/* ----------------------------------------------------------------------------- research */
function tabResearch() {
  const r = STATE.research;
  const tab = $('#tab');
  const actions = `
    <div class="row">
      <button class="btn btn-primary" id="r-run" ${llm() ? '' : 'disabled'}>Run research with Claude</button>
      <button class="btn" id="r-verify" ${r ? '' : 'disabled'}>Re-check sources & quotes</button>
      <button class="btn" id="r-import">Import research JSON</button>
      <button class="btn btn-ok" id="r-approve" ${r && r.sufficiency.enough && !r.approved ? '' : 'disabled'}>${r && r.approved ? '✓ Approved' : 'Approve research'}</button>
    </div>`;
  if (!r) {
    tab.innerHTML = `<div class="card">${actions}<div style="margin-top:12px">${llm() ? '<p class="muted">Claude will search the web, open every source it uses, and extract claims with verbatim quotes. The app then re-checks every quote against the retrieved page text.</p>' : ccHint('/reel-research', 'research the topic with web search, capture verbatim quotes and import them')}</div></div>${manualSourceCard()}`;
    bindResearch();
    return;
  }
  const counts = r.claims.reduce((a, c) => ((a[c.status] = (a[c.status] || 0) + 1), a), {});
  const src = Object.fromEntries(r.sources.map((s) => [s.id, s]));
  tab.innerHTML = `
    <div class="banner ${r.sufficiency.enough ? 'ok' : 'bad'}"><b>${r.sufficiency.enough ? 'Enough reliable information for an accurate reel.' : 'NOT enough reliable information.'}</b> ${esc(r.sufficiency.reason)}</div>
    <div class="card">${actions}<div class="small muted" style="margin-top:8px">Method: ${esc(r.method)} · ${r.sources.length} sources · ${Object.entries(counts).map(([k, v]) => `${v} ${k.replace('_', ' ')}`).join(' · ')}</div></div>
    <div class="card"><h3>Summary</h3><p>${esc(r.summary)}</p>${r.angles.length ? `<h3>Angles supported by evidence</h3><ul>${r.angles.map((a) => `<li>${esc(a)}</li>`).join('')}</ul>` : ''}
      ${r.uncertainties.length ? `<h3>Disputed / uncertain</h3><ul>${r.uncertainties.map((a) => `<li>${esc(a)}</li>`).join('')}</ul>` : ''}</div>
    <div class="card"><h3>Claims</h3><table><thead><tr><th>ID</th><th>Claim</th><th>Status</th><th>Evidence</th><th>Use</th></tr></thead><tbody>
      ${r.claims.map((c) => `<tr>
        <td class="mono">${esc(c.id)}</td>
        <td>${esc(c.statement)}<div class="small muted">${esc(c.category)} · ${esc(c.certainty)}${c.as_of ? ' · as of ' + esc(c.as_of) : ''}${c.caveats ? ' · ' + esc(c.caveats) : ''}</div><div class="small muted">${esc(c.notes)}</div></td>
        <td>${badge(c.status)}</td>
        <td>${c.evidence.map((e) => `<div>${badge(e.verification)} <a href="${esc(src[e.source_id]?.url)}" target="_blank" rel="noopener">${esc(e.source_id)} ${esc(src[e.source_id]?.publisher || '')}</a><details><summary>quote</summary><blockquote>${esc(e.quote)}</blockquote></details></div>`).join('')}</td>
        <td><input type="checkbox" data-claim="${esc(c.id)}" ${c.use_in_script ? 'checked' : ''}></td></tr>`).join('')}
    </tbody></table></div>
    <div class="card"><h3>Sources</h3><table><thead><tr><th>ID</th><th>Source</th><th>Tier</th><th>Primary</th><th>Accessed</th><th>Snapshot</th></tr></thead><tbody>
      ${r.sources.map((s) => `<tr><td class="mono">${esc(s.id)}</td><td><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.publisher)}</a><div class="small muted">${esc(s.title)}</div><div class="small muted">${esc(s.notes)}</div></td>
        <td>${badge(['government', 'intergovernmental', 'academic', 'company_official'].includes(s.tier) ? 'verified' : 'info', s.tier)}</td><td>${s.primary ? 'yes' : 'no'}</td>
        <td class="small">${esc((s.accessed_at || '').slice(0, 10))}<div class="muted">${esc(s.access_method)}</div></td>
        <td>${s.snapshot_file ? `<a href="/files/${esc(PID)}/${esc(s.snapshot_file)}" target="_blank">${esc(s.snapshot_kind)}</a>` : '-'}</td></tr>`).join('')}
    </tbody></table>
    <div class="row" style="margin-top:10px"><a class="btn btn-sm" href="/files/${esc(PID)}/research.md" target="_blank">Open research.md</a></div></div>
    ${manualSourceCard()}`;
  bindResearch();
  tab.querySelectorAll('[data-claim]').forEach((cb) => (cb.onchange = async () => {
    try { await api.post(`/api/projects/${PID}/research/claims/${cb.dataset.claim}`, {use_in_script: cb.checked}); toast('Claim updated - re-approve research'); refresh(); } catch (e) { toast(e.message, true); }
  }));
}

function manualSourceCard() {
  const r = STATE.research;
  return `<div class="card"><h3>Add evidence manually</h3>
    <div class="grid2"><div><label>Source URL (the app downloads it; inaccessible sources are refused)</label><input id="m-url" type="url" placeholder="https://..."></div>
    <div style="align-self:end"><button class="btn" id="m-add-src">Fetch & add source</button></div></div>
    ${r && r.sources.length ? `<div class="grid3"><div><label>Claim (plain statement)</label><input id="m-stmt" type="text"></div>
      <div><label>Source</label><select id="m-src">${r.sources.map((s) => `<option value="${esc(s.id)}">${esc(s.id)} ${esc(s.publisher)}</option>`).join('')}</select></div>
      <div><label>Verbatim quote from that page</label><input id="m-quote" type="text"></div></div>
      <div class="row" style="margin-top:10px"><button class="btn" id="m-add-claim">Add & verify claim</button></div>` : ''}
    <input type="file" id="r-file" accept="application/json" class="hidden"></div>`;
}

function bindResearch() {
  const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  on('#r-run', () => startJob(`/api/projects/${PID}/stages/research`));
  on('#r-verify', () => startJob(`/api/projects/${PID}/stages/verify_sources`));
  on('#r-approve', async () => { try { await api.post(`/api/projects/${PID}/research/approve`); toast('Research approved'); refresh(); } catch (e) { toast(e.message, true); } });
  on('#r-import', () => $('#r-file').click());
  const f = $('#r-file');
  if (f) f.onchange = async () => {
    try { const data = JSON.parse(await f.files[0].text()); const r = await api.post(`/api/projects/${PID}/research/import`, data); toast(`Imported ${r.claims} claims`); refresh(); } catch (e) { toast(e.message, true); }
  };
  on('#m-add-src', async () => { try { await api.post(`/api/projects/${PID}/research/sources`, {url: $('#m-url').value}); toast('Source added'); refresh(); } catch (e) { toast(e.message, true); } });
  on('#m-add-claim', async () => {
    try { const c = await api.post(`/api/projects/${PID}/research/claims`, {statement: $('#m-stmt').value, source_id: $('#m-src').value, quote: $('#m-quote').value}); toast(`${c.id}: ${c.status}`); refresh(); } catch (e) { toast(e.message, true); }
  });
}

/* ----------------------------------------------------------------------------- script */
function tabScript() {
  const s = STATE.script;
  const r = STATE.research;
  const tab = $('#tab');
  const usable = r ? r.claims.filter((c) => c.use_in_script && ['verified', 'single_source', 'conflicting'].includes(c.status)) : [];
  const actions = `<div class="row">
      <button class="btn btn-primary" id="s-write" ${llm() && r && r.approved ? '' : 'disabled'}>${s ? 'Rewrite with Claude' : 'Write script with Claude'}</button>
      <button class="btn" id="s-save" ${s ? '' : 'disabled'}>Save & validate</button>
      <button class="btn" id="s-add">+ Add beat</button>
      <button class="btn btn-ok" id="s-approve" ${s && !s.approved ? '' : 'disabled'}>${s && s.approved ? '✓ Approved' : 'Approve script'}</button></div>`;
  if (!r || !r.approved) {
    tab.innerHTML = `<div class="card"><p>Approve the research first - the script may only use verified claims.</p></div>`;
    return;
  }
  const beats = s ? s.beats : [{id: 'B1', section: 'hook', text: '', claim_ids: [], emphasis: [], on_screen_text: ''}];
  const issuesFor = (bid) => (s ? s.issues.filter((i) => i.beat_id === bid) : []);
  tab.innerHTML = `
    <div class="card">${actions}${!llm() ? ccHint('/reel-script', 'write the script from the verified claims') : ''}
      ${s ? `<div class="small muted" style="margin-top:8px">Version ${s.version} · written by ${esc(s.written_by)} · ${s.beats.length} beats</div>` : ''}</div>
    <div class="card"><div class="grid2"><div><label>Reel title</label><input id="s-title" type="text" value="${esc(s ? s.title : STATE.project.settings.topic)}"></div>
      <div><label>Closing question</label><input id="s-cta" type="text" value="${esc(s ? s.cta_question : '')}"></div></div></div>
    <div class="card" id="beats">${beats.map((b) => beatRow(b, usable, issuesFor(b.id))).join('')}</div>
    ${s ? `<div class="card"><h3>Validation</h3>${s.issues.filter((i) => !i.beat_id).map((i) => `<div class="issue ${esc(i.severity)}">● ${esc(i.message)}</div>`).join('') || '<div class="muted small">No script-level issues.</div>'}</div>` : ''}
    <div class="card"><h3>Claims available</h3>${usable.map((c) => `<div class="small"><span class="mono">${esc(c.id)}</span> ${badge(c.status)} ${esc(c.statement)}</div>`).join('')}</div>`;
  const collect = () => ({
    title: $('#s-title').value, cta_question: $('#s-cta').value, hook_type: s ? s.hook_type : '',
    beats: [...document.querySelectorAll('.beat')].map((el, i) => ({
      id: `B${i + 1}`, section: $('.b-section', el).value, text: $('.b-text', el).value.trim(),
      claim_ids: $('.b-claims', el).value.split(',').map((x) => x.trim()).filter(Boolean),
      emphasis: $('.b-emph', el).value.split(',').map((x) => x.trim()).filter(Boolean),
      on_screen_text: $('.b-ost', el).value.trim() || null,
    })).filter((b) => b.text),
  });
  const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  on('#s-write', () => startJob(`/api/projects/${PID}/stages/script`));
  on('#s-save', async () => { try { const r2 = await api.put(`/api/projects/${PID}/script`, collect()); toast(`Saved v${r2.version}: ${r2.issues.filter((i) => i.severity === 'error').length} error(s)`); refresh(); } catch (e) { toast(e.message, true); } });
  on('#s-add', () => { $('#beats').insertAdjacentHTML('beforeend', beatRow({id: '', section: 'story', text: '', claim_ids: [], emphasis: [], on_screen_text: ''}, usable, [])); });
  on('#s-approve', async () => {
    try { await api.put(`/api/projects/${PID}/script`, collect()); await api.post(`/api/projects/${PID}/script/approve`); toast('Script approved'); refresh(); } catch (e) { toast(e.message, true); refresh(); }
  });
  tab.querySelectorAll('.b-del').forEach((b) => (b.onclick = () => b.closest('.beat').remove()));
}

function beatRow(b, usable, issues) {
  const secs = ['hook', 'context', 'story', 'payoff', 'ending'];
  return `<div class="beat"><div class="beat-side"><span class="mono">${esc(b.id || 'new')}</span>
      <select class="b-section">${secs.map((x) => `<option ${x === b.section ? 'selected' : ''}>${x}</option>`).join('')}</select>
      <button class="btn btn-sm btn-danger b-del">Remove</button></div>
    <div><textarea class="b-text" placeholder="Narration sentence">${esc(b.text)}</textarea>
      <div class="grid3"><div><label>Claim IDs</label><input class="b-claims" type="text" value="${esc(b.claim_ids.join(', '))}" placeholder="C1, C4"></div>
        <div><label>Emphasis</label><input class="b-emph" type="text" value="${esc(b.emphasis.join(', '))}"></div>
        <div><label>On-screen headline</label><input class="b-ost" type="text" value="${esc(b.on_screen_text || '')}"></div></div>
      ${issues.map((i) => `<div class="issue ${esc(i.severity)}">● ${esc(i.message)}</div>`).join('')}</div></div>`;
}

/* ----------------------------------------------------------------------------- storyboard */
function tabStoryboard() {
  const sb = STATE.storyboard;
  const s = STATE.script;
  const tab = $('#tab');
  if (!s || !s.approved) { tab.innerHTML = '<div class="card">Approve the script first.</div>'; return; }
  const tl = STATE.timeline;
  const actions = `<div class="row">
    <button class="btn btn-primary" id="b-plan">${sb ? 'Re-plan storyboard' : 'Plan storyboard'}${llm() ? ' (Claude)' : ' (rules)'}</button>
    <button class="btn" id="b-save" ${sb ? '' : 'disabled'}>Save edits</button>
    <button class="btn" id="b-voice">${tl ? 'Re-generate voice-over' : 'Generate voice-over'}</button>
    <button class="btn" id="b-assets" ${sb ? '' : 'disabled'}>Find stock media</button>
    <button class="btn" id="b-stills" ${sb && tl ? '' : 'disabled'}>Render storyboard stills</button></div>`;
  if (!sb) { tab.innerHTML = `<div class="card">${actions}</div>`; bindSB(); return; }
  const assets = Object.fromEntries(STATE.assets.assets.map((a) => [a.id, a]));
  const times = tl ? Object.fromEntries(tl.scenes.map((x) => [x.scene_id, x])) : {};
  const issues = STATE.storyboard_issues || [];
  const kinds = ['footage', 'photo', 'map', 'stat', 'chart', 'timeline', 'kinetic', 'comparison', 'icon', 'quote', 'title'];
  const trans = ['cut', 'fade', 'slide_up', 'slide_left', 'zoom', 'whip', 'wipe'];
  tab.innerHTML = `<div class="card">${actions}<div class="small muted" style="margin-top:8px">${sb.scenes.length} scenes · planned by ${esc(sb.planned_by)} · music: ${esc(sb.music_mood)}${tl ? ` · voice-over ${tl.duration.toFixed(1)}s (${esc(tl.alignment)})` : ''}</div>
      ${STATE.narration_url ? `<audio controls src="${esc(STATE.narration_url)}" style="width:100%;margin-top:10px"></audio>` : ''}</div>
    ${issues.length ? `<div class="banner bad">${issues.map((i) => `<div>● ${esc(i.message)}</div>`).join('')}</div>` : ''}
    <div class="scenes">${sb.scenes.map((sc) => {
      const beatText = sc.beat_ids.map((b) => s.beats.find((x) => x.id === b)?.text || '').join(' ');
      const thumb = STATE.previews[sc.id] ? `<video src="${esc(STATE.previews[sc.id])}" controls muted></video>` : (STATE.stills[sc.id] || STATE.thumbs[sc.id]) ? `<img src="${esc(STATE.stills[sc.id] || STATE.thumbs[sc.id])}">` : `${esc(sc.visual.kind)}<br>no still yet`;
      const a = assets[sc.visual.asset_id];
      const cands = (sc.visual.candidate_ids || []).map((id) => assets[id]).filter(Boolean);
      const t = times[sc.id];
      return `<div class="scene" data-sid="${esc(sc.id)}"><div class="scene-thumb">${thumb}</div><div class="scene-body">
        <div class="row spread"><span class="kind">${esc(sc.id)} · ${esc(sc.visual.kind)}</span><span class="small muted">${t ? `${t.start.toFixed(1)}-${t.end.toFixed(1)}s` : ''}</span></div>
        <div class="small" style="margin:4px 0 6px">${esc(beatText)}</div>
        <div class="grid2"><div><label>Visual</label><select class="sc-kind">${kinds.map((k) => `<option ${k === sc.visual.kind ? 'selected' : ''}>${k}</option>`).join('')}</select></div>
          <div><label>Transition</label><select class="sc-trans">${trans.map((k) => `<option ${k === sc.transition ? 'selected' : ''}>${k}</option>`).join('')}</select></div></div>
        <label>Purpose</label><input class="sc-purpose" type="text" value="${esc(sc.visual.purpose)}">
        <label>Stock queries (comma separated)</label><input class="sc-q" type="text" value="${esc(sc.visual.queries.join(', '))}">
        <details><summary>Parameters (JSON)</summary><textarea class="sc-params mono">${esc(JSON.stringify(sc.visual.params, null, 1))}</textarea></details>
        ${a ? `<div class="small muted" style="margin-top:6px">Media: ${esc(a.provider)} · ${esc(a.author)} · ${esc(a.license)}</div>` : ''}
        ${cands.length > 1 ? `<label>Swap media</label><select class="sc-swap">${cands.map((c) => `<option value="${esc(c.id)}" ${c.id === sc.visual.asset_id ? 'selected' : ''}>${esc(c.provider)}: ${esc((c.title || '').slice(0, 40))} (${c.relevance})</option>`).join('')}</select>` : ''}
        <div class="row" style="margin-top:8px">
          <input class="sc-instr" type="text" placeholder="e.g. use a map instead" style="flex:1;min-width:120px">
          <button class="btn btn-sm sc-regen" ${llm() ? '' : 'disabled'}>Regenerate</button>
          <button class="btn btn-sm sc-prev" ${tl ? '' : 'disabled'}>Preview</button></div>
      </div></div>`;
    }).join('')}</div>`;
  bindSB();
  tab.querySelectorAll('.scene').forEach((el) => {
    const sid = el.dataset.sid;
    $('.sc-regen', el).onclick = () => startJob(`/api/projects/${PID}/storyboard/scenes/${sid}/regenerate`, {instruction: $('.sc-instr', el).value});
    $('.sc-prev', el).onclick = () => startJob(`/api/projects/${PID}/storyboard/scenes/${sid}/preview`);
    const sw = $('.sc-swap', el);
    if (sw) sw.onchange = async () => { try { await api.post(`/api/projects/${PID}/storyboard/scenes/${sid}/swap`, {asset_id: sw.value}); toast('Media swapped'); refresh(); } catch (e) { toast(e.message, true); } };
  });
}

function bindSB() {
  const on = (id, fn) => { const el = $(id); if (el) el.onclick = fn; };
  on('#b-plan', () => startJob(`/api/projects/${PID}/stages/storyboard`));
  on('#b-voice', () => startJob(`/api/projects/${PID}/stages/voice`));
  on('#b-assets', () => startJob(`/api/projects/${PID}/stages/assets`));
  on('#b-stills', () => startJob(`/api/projects/${PID}/stills`));
  on('#b-save', async () => {
    const sb = JSON.parse(JSON.stringify(STATE.storyboard));
    for (const el of document.querySelectorAll('.scene')) {
      const sc = sb.scenes.find((x) => x.id === el.dataset.sid);
      sc.visual.kind = $('.sc-kind', el).value;
      sc.transition = $('.sc-trans', el).value;
      sc.visual.purpose = $('.sc-purpose', el).value;
      sc.visual.queries = $('.sc-q', el).value.split(',').map((x) => x.trim()).filter(Boolean);
      try { sc.visual.params = JSON.parse($('.sc-params', el).value || '{}'); } catch { return toast(`${sc.id}: parameters are not valid JSON`, true); }
    }
    try { const r = await api.put(`/api/projects/${PID}/storyboard`, sb); toast(r.issues.length ? `${r.issues.length} issue(s) found` : 'Storyboard saved'); refresh(); } catch (e) { toast(e.message, true); }
  });
}

/* ----------------------------------------------------------------------------- produce */
function tabProduce() {
  const tab = $('#tab');
  const st = STATE.project.stages;
  const ready = STATE.script?.approved && STATE.storyboard;
  const rows = ['voice', 'assets', 'render', 'package', 'qc'].map((k) => `<tr><td>${dot(st[k]?.status)} ${k}</td><td>${badge(st[k]?.status || 'pending')}</td><td class="small muted">${esc(st[k]?.message || '')}</td>
    <td><button class="btn btn-sm" data-stage="${k}" ${ready ? '' : 'disabled'}>Run</button></td></tr>`).join('');
  tab.innerHTML = `<div class="card"><div class="row"><button class="btn btn-primary" id="p-all" ${ready ? '' : 'disabled'}>Generate final video (voice → media → render → caption → QC)</button></div>
      <p class="small muted">Rendering a 60-second reel takes a few minutes on a laptop CPU. Quality checks run automatically; a reel is marked complete only if no critical check fails.</p></div>
    <div class="card"><h3>Stages</h3><table><tbody>${rows}</tbody></table></div>
    <div class="card"><h3>Music</h3><p class="small muted">By default an original score is composed for each reel (no licensing issues). To use a licensed track instead, upload it with its licence.</p>
      <div class="row"><input type="file" id="m-file" accept="audio/*"><input type="text" id="m-lic" placeholder="Licence (e.g. Pixabay Content License, track URL)" style="flex:1"><button class="btn" id="m-up">Upload music</button></div></div>
    <div class="card"><h3>Your own media</h3><p class="small muted">Add footage or photos you own or have licensed. Mark whether it is documentary evidence of the subject.</p>
      <div class="grid3"><div><input type="file" id="a-file" accept="video/*,image/*"></div><div><input type="text" id="a-author" placeholder="Author / owner"></div><div><input type="text" id="a-lic" placeholder="Licence"></div></div>
      <div class="row" style="margin-top:8px"><select id="a-scene"><option value="">(add to library only)</option>${(STATE.storyboard?.scenes || []).map((s) => `<option>${esc(s.id)}</option>`).join('')}</select>
      <select id="a-auth"><option value="documentary">Documentary (shows the real subject)</option><option value="representative">Representative</option></select><button class="btn" id="a-up">Upload</button></div></div>`;
  $('#p-all').onclick = () => startJob(`/api/projects/${PID}/produce`);
  tab.querySelectorAll('[data-stage]').forEach((b) => (b.onclick = () => startJob(`/api/projects/${PID}/stages/${b.dataset.stage}`)));
  $('#m-up').onclick = async () => {
    const f = $('#m-file').files[0]; if (!f || !$('#m-lic').value) return toast('Choose a file and enter its licence', true);
    const fd = new FormData(); fd.append('file', f); fd.append('license', $('#m-lic').value);
    try { await api.upload(`/api/projects/${PID}/music`, fd); toast('Music uploaded - re-render to use it'); } catch (e) { toast(e.message, true); }
  };
  $('#a-up').onclick = async () => {
    const f = $('#a-file').files[0]; if (!f || !$('#a-lic').value || !$('#a-author').value) return toast('File, author and licence are required', true);
    const fd = new FormData(); fd.append('file', f); fd.append('license', $('#a-lic').value); fd.append('author', $('#a-author').value);
    fd.append('authenticity', $('#a-auth').value); if ($('#a-scene').value) fd.append('scene_id', $('#a-scene').value);
    try { await api.upload(`/api/projects/${PID}/assets/upload`, fd); toast('Media added'); refresh(); } catch (e) { toast(e.message, true); }
  };
}

/* ----------------------------------------------------------------------------- publish */
function tabPublish() {
  const tab = $('#tab');
  const f = STATE.files;
  const qc = STATE.qc;
  const pkg = STATE.package;
  if (!f.reel) { tab.innerHTML = '<div class="card">No video yet - generate it in the Produce step.</div>'; return; }
  const copy = (id, text, title) => `<div class="card"><h3>${esc(title)}</h3><div class="copy-box"><pre id="${id}">${esc(text)}</pre><button class="btn btn-sm" data-copy="${id}">Copy</button></div></div>`;
  tab.innerHTML = `
    ${qc ? `<div class="banner ${qc.passed ? 'ok' : 'bad'}"><b>${esc(qc.summary)}</b></div>` : '<div class="banner warn">Quality check has not run yet.</div>'}
    <div class="player card"><video src="${esc(f.reel)}" controls playsinline></video>
      <div><h2>${esc(pkg?.title || STATE.script?.title || '')}</h2>
        <div class="row" style="margin:10px 0">${f.cover ? `<img class="cover-img" src="${esc(f.cover)}">` : ''}${f.cover_grid ? `<img class="cover-img" src="${esc(f.cover_grid)}" title="profile grid crop">` : ''}</div>
        <div class="row">
          <a class="btn btn-primary" href="${esc(f.reel)}?download=1">Download MP4</a>
          ${f.cover ? `<a class="btn" href="${esc(f.cover)}?download=1">Cover</a>` : ''}
          ${f.srt ? `<a class="btn" href="${esc(f.srt)}?download=1">Captions .srt</a>` : ''}
          ${f.vtt ? `<a class="btn" href="${esc(f.vtt)}?download=1">.vtt</a>` : ''}
          ${f.research ? `<a class="btn" href="${esc(f.research)}?download=1">Research</a>` : ''}
          ${f.sources ? `<a class="btn" href="${esc(f.sources)}?download=1">Sources</a>` : ''}
          ${f.credits ? `<a class="btn" href="${esc(f.credits)}?download=1">Credits</a>` : ''}
          <a class="btn" href="/api/projects/${esc(PID)}/bundle.zip">Everything (.zip)</a>
        </div>
        ${pkg ? `<p class="small muted" style="margin-top:12px">Hashtags: ${esc(pkg.hashtags.join(' '))}</p><p class="small"><b>CTA:</b> ${esc(pkg.cta)}</p><p class="small"><b>Alt text:</b> ${esc(pkg.alt_text)}</p>` : ''}
      </div></div>
    ${STATE.caption_full ? copy('cap', STATE.caption_full, 'Caption (with sources and hashtags)') : ''}
    ${pkg ? copy('pin', pkg.pinned_comment, 'Pinned comment') : ''}
    ${qc ? `<div class="card"><h3>Quality report</h3><table><thead><tr><th>Result</th><th>Severity</th><th>Check</th><th>Details</th></tr></thead><tbody>
      ${qc.checks.map((c) => `<tr><td>${badge(c.status)}</td><td class="small">${esc(c.severity)}</td><td>${esc(c.name)}</td><td class="small">${esc(c.details)}</td></tr>`).join('')}</tbody></table>
      <div class="row" style="margin-top:10px"><button class="btn" id="q-run">Re-run QC</button></div></div>` : ''}`;
  tab.querySelectorAll('[data-copy]').forEach((b) => (b.onclick = () => { navigator.clipboard.writeText($('#' + b.dataset.copy).textContent); toast('Copied'); }));
  const q = $('#q-run'); if (q) q.onclick = () => startJob(`/api/projects/${PID}/stages/qc`);
}

init().catch((e) => { document.body.innerHTML = `<pre style="color:#f88;padding:20px">${esc(e.stack || e)}</pre>`; });
