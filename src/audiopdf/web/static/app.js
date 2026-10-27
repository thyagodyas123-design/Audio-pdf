'use strict';
/* Audio-PDF · interface local. Vanilla JS, sem build. Todo texto de usuário entra por textContent (nunca innerHTML). */

// ---------- utilitários ----------
const $ = (s, r = document) => r.querySelector(s);
const $app = $('#app');
const store = {
  get(k, d = null) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* modo privado */ } },
};
const ICONS = {
  play: '<path d="M8 5.5v13l11-6.5z" fill="currentColor" stroke="none"/>',
  pause: '<path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z" fill="currentColor" stroke="none"/>',
  back: '<path d="M4 12a8 8 0 1 0 2.6-5.9"/><path d="M4 4v4.6h4.6"/><text x="12" y="15.3" font-size="7.6" text-anchor="middle" fill="currentColor" stroke="none" font-weight="600" font-family="DM Sans, sans-serif">30</text>',
  fwd: '<path d="M20 12a8 8 0 1 1-2.6-5.9"/><path d="M20 4v4.6h-4.6"/><text x="12" y="15.3" font-size="7.6" text-anchor="middle" fill="currentColor" stroke="none" font-weight="600" font-family="DM Sans, sans-serif">30</text>',
  download: '<path d="M12 4v11M7 11l5 5 5-5M5 20h14"/>',
  upload: '<path d="M12 16V5M7 9l5-4 5 4M5 20h14"/>',
  trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13"/>',
  refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>',
  check: '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4 8 8 0 1 0 20 14.5z"/>',
  search: '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  more: '<circle cx="5" cy="12" r="1.4" fill="currentColor"/><circle cx="12" cy="12" r="1.4" fill="currentColor"/><circle cx="19" cy="12" r="1.4" fill="currentColor"/>',
  alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17.2v.1"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.1"/>',
  video: '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10.5l5-3v9l-5-3z"/>',
  book: '<path d="M12 6.5C10.5 5 8 4.5 4.5 4.5v13c3.5 0 6 .5 7.5 2 1.5-1.5 4-2 7.5-2v-13c-3.5 0-6 .5-7.5 2zM12 6.5v13"/>',
  chevl: '<path d="M14.5 6l-6 6 6 6"/>',
  chevr: '<path d="M9.5 6l6 6-6 6"/>',
  user: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"/>',
  out: '<path d="M10 5H6a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h4M15 8l4 4-4 4M19 12H9"/>',
  edit: '<path d="M5 19l1-4L16.5 4.5a1.8 1.8 0 0 1 2.5 2.5L8.5 17.5z"/>',
};
function ic(name, size = 20) {
  const s = document.createElement('span');
  s.className = 'ic';
  s.innerHTML = `<svg width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`; // ICONS é constante local
  return s;
}
function h(tag, props = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'value' || k === 'checked' || k === 'disabled' || k === 'hidden') el[k] = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, v);
  }
  for (const k of kids.flat(Infinity)) if (k != null && k !== false) el.append(k.nodeType ? k : document.createTextNode(String(k)));
  return el;
}
async function api(url, opts) {
  const r = await fetch(url, opts);
  if (!r.ok) {
    let d = r.statusText || `Erro ${r.status}`;
    try { d = (await r.json()).detail || d; } catch { /* corpo não JSON */ }
    const err = new Error(typeof d === 'string' ? d : 'Erro inesperado');
    err.status = r.status;
    throw err;
  }
  return r.json();
}
const send = (method) => (url, body) => api(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
const post = send('POST'), patch = send('PATCH');

const pad2 = (n) => String(n).padStart(2, '0');
function fmtDur(s) {
  s = Math.round(s || 0);
  if (s < 60) return `${s} s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${pad2(m % 60)} min`;
}
function fmtClock(s) {
  s = Math.max(0, Math.floor(s || 0));
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = s % 60;
  return hh ? `${hh}:${pad2(mm)}:${pad2(ss)}` : `${mm}:${pad2(ss)}`;
}
const CHARS_PER_SEC = 17; // texto por segundo de áudio (medido com Kokoro)
const PROCESS_FACTOR = 4.5; // vezes tempo real, aproximado e dependente do hardware
const COVERS = ['#17415C', '#6B2D3A', '#2F4A3A', '#3A3556', '#5A3D1F', '#1F4D4A', '#4A2F4F', '#2E3F57'];
const hashN = (s) => [...s].reduce((a, c) => (a * 31 + c.charCodeAt(0)) >>> 0, 7);
function cover(title, id, mini = false) {
  const el = h('div', { class: mini ? 'cover mini' : 'cover', style: `background:${COVERS[hashN(id) % COVERS.length]}`, 'aria-hidden': 'true' });
  if (mini) { el.append(h('b', {}, (title.match(/\p{L}/gu) || ['A']).slice(0, 2).join('').toUpperCase())); return el; }
  el.append(h('b', {}, title));
  return el;
}

// ---------- toasts e diálogos ----------
function toast(msg, kind = '') {
  const t = h('div', { class: `toast ${kind}` }, msg);
  $('#toasts').append(t);
  setTimeout(() => t.remove(), kind === 'err' ? 7000 : 3500);
}
function confirmDialog({ title, body, ok = 'Confirmar', danger = false }) {
  return new Promise((resolve) => {
    const dlg = h('dialog', { 'aria-labelledby': 'dlg-t' },
      h('h2', { id: 'dlg-t' }, title), h('p', { class: 'muted', style: 'margin:0' }, body),
      h('div', { class: 'row' },
        h('button', { class: 'btn', onclick: () => dlg.close('no') }, 'Cancelar'),
        h('button', { class: `btn ${danger ? 'danger' : 'primary'}`, onclick: () => dlg.close('yes') }, ok)));
    dlg.addEventListener('close', () => { resolve(dlg.returnValue === 'yes'); dlg.remove(); });
    document.body.append(dlg);
    dlg.showModal();
  });
}

// ---------- status ----------
const STATUS = {
  done: ['Pronto', ''], running: ['Narrando', 'run'], translating: ['Traduzindo', 'run'], queued: ['Na fila', 'run'],
  failed: ['Falhou', 'fail'], canceled: ['Cancelado', 'warn'], idle: ['Não convertido', 'idle'],
};
const chip = (s) => { const [t, k] = STATUS[s] || [s, 'idle']; return h('span', { class: `chip ${k}` }, t); };
const playable = (c) => c.status === 'done' || (c.status === 'running' && c.parts > 0); // `parts` só vale enquanto converte
const isBusy = (c) => c.status === 'running' || c.status === 'queued' || c.status === 'translating';
const vBusy = (c) => Object.values(c.videos || {}).some((v) => v.status === 'queued' || v.status === 'running');
const metaBusy = (m) => m.chapters.some((c) => isBusy(c) || vBusy(c));

// ---------- player global ----------
const P = {
  a: $('#audio'), bar: $('#player'), meta: null, idx: null, live: null, waiting: false,
  rate: store.get('rate', 1), sleep: null, sleepT: null, dragging: false, lastSave: 0, subs: new Set(), pollT: null,
  chapter(i) { return this.meta && this.meta.chapters.find((c) => c.index === i); },
  get playing() { return !this.a.paused && !this.a.ended; },
  emit() { this.subs.forEach((f) => f()); },

  async open(bookId, idx) {
    try {
      if (!this.meta || this.meta.id !== bookId) this.meta = await api(`/api/books/${bookId}`);
      this.start(idx);
    } catch (e) { toast(e.message, 'err'); }
  },
  resumeAt(idx) { return store.get(`pos:${this.meta.id}:${idx}`, 0); },
  start(idx, at = null) {
    const c = this.chapter(idx);
    if (!c) return;
    this.waiting = false;
    this.idx = idx;
    if (c.status === 'done') {
      this.live = null;
      const t = at ?? this.resumeAt(idx);
      this.a.src = `/api/books/${this.meta.id}/audio/${idx}`;
      this.a.addEventListener('loadedmetadata', () => {
        if (t > 3 && t < this.a.duration - 5) this.a.currentTime = t;
        this.a.play().catch(() => {});
      }, { once: true });
    } else if (playable(c)) {
      this.startPart(idx, 0);
    } else {
      toast('Esse capítulo ainda não tem áudio. Converta-o primeiro.');
      return;
    }
    this.a.playbackRate = this.rate;
    this.prefetch(idx);
    this.show();
    this.paint();
    this.session();
    this.emit();
  },
  startPart(idx, p) {
    this.live = { idx, part: p };
    this.a.src = `/api/books/${this.meta.id}/parts/${idx}/${p}`;
    this.a.playbackRate = this.rate;
    this.a.play().catch(() => {});
    this.paint();
    this.emit();
  },
  prefetch(idx) {
    post(`/api/books/${this.meta.id}/prefetch/${idx}`).then(() => this.refresh()).catch(() => {});
  },
  toggle() {
    if (!this.meta) return;
    if (this.a.paused) this.a.play().catch(() => {}); else this.a.pause();
  },
  skip(d) { if (Number.isFinite(this.a.duration)) this.a.currentTime = Math.min(this.a.duration, Math.max(0, this.a.currentTime + d)); },
  advance() {
    const next = this.chapter(this.idx + 1);
    if (next && playable(next)) this.start(next.index, 0);
    else if (next) { this.waiting = true; this.live = { idx: next.index, part: -1 }; this.paint(); }
    else { this.a.pause(); toast('Fim do livro.'); }
  },
  onEnded() {
    store.set(`pos:${this.meta.id}:${this.idx}`, 0);
    if (this.sleep === 'chapter') { this.setSleep(null); toast('Timer de sono: pausado ao fim do capítulo.'); return; }
    if (!this.live) return this.advance();
    const c = this.chapter(this.live.idx);
    if (c.parts > this.live.part + 1) return this.startPart(this.live.idx, this.live.part + 1);
    if (c.status === 'done') return this.advance();
    this.waiting = true;
    this.paint();
  },
  checkWaiting() {
    if (!this.waiting || !this.live) return;
    const c = this.chapter(this.live.idx);
    if (!c) return;
    if (this.live.part === -1) { if (playable(c)) this.start(c.index, 0); return; }
    if (c.parts > this.live.part + 1) this.startPart(this.live.idx, this.live.part + 1);
    else if (c.status === 'done') this.advance();
  },
  setMeta(m) {
    if (this.meta && this.meta.id === m.id) { this.meta = m; this.checkWaiting(); this.paint(); this.emit(); this.schedule(); }
  },
  async refresh() {
    if (!this.meta) return;
    try { this.setMeta(await api(`/api/books/${this.meta.id}`)); } catch { /* livro removido */ }
  },
  schedule() {
    clearTimeout(this.pollT);
    if (this.meta && (this.waiting || metaBusy(this.meta))) this.pollT = setTimeout(() => this.refresh(), 2500);
  },
  setSleep(v) {
    this.sleep = v;
    clearTimeout(this.sleepT);
    if (typeof v === 'number') this.sleepT = setTimeout(() => { this.a.pause(); this.setSleep(null); toast('Timer de sono: reprodução pausada.'); }, v * 60000);
    this.paint();
  },
  cycleSleep() {
    const seq = [null, 15, 30, 60, 'chapter'];
    this.setSleep(seq[(seq.indexOf(this.sleep) + 1) % seq.length]);
  },
  cycleRate() {
    const seq = [0.75, 1, 1.25, 1.5, 1.75, 2];
    this.rate = seq[(seq.indexOf(this.rate) + 1) % seq.length] ?? 1;
    this.a.playbackRate = this.rate;
    store.set('rate', this.rate);
    this.paint();
  },
  show() {
    this.bar.hidden = false;
    requestAnimationFrame(() => { this.bar.classList.add('on'); this.fit(); });
  },
  fit() { document.documentElement.style.setProperty('--player-h', this.bar.classList.contains('on') ? `${this.bar.offsetHeight}px` : '0px'); },
  close() {
    if (R.isOpen) R.hide();
    this.a.pause(); this.a.removeAttribute('src'); this.meta = null; this.idx = null; this.live = null; this.waiting = false;
    this.setSleep(null); clearTimeout(this.pollT);
    this.bar.classList.remove('on'); this.fit();
    setTimeout(() => { if (!this.meta) this.bar.hidden = true; }, 400);
    if ('mediaSession' in navigator) navigator.mediaSession.metadata = null;
    this.emit();
  },
  save(force = false) {
    if (!this.meta || this.live || !Number.isFinite(this.a.currentTime)) return;
    const now = Date.now();
    if (!force && now - this.lastSave < 4000) return;
    this.lastSave = now;
    store.set(`pos:${this.meta.id}:${this.idx}`, this.a.currentTime);
    store.set('last', { b: this.meta.id, i: this.idx, t: this.a.currentTime });
  },
  paint() {
    if (!this.meta || this.idx == null) return;
    const c = this.chapter(this.live && this.live.idx != null ? this.live.idx : this.idx) || this.chapter(this.idx);
    $('#pl-title').textContent = c ? `${pad2(c.index)} · ${c.title}` : '';
    $('#pl-sub').textContent = this.waiting ? 'Aguardando a conversão…'
      : this.live && c && c.status !== 'done' ? `${this.meta.title} · pré-escuta, o capítulo ainda está sendo convertido` : this.meta.title;
    const cv = $('#pl-cover'); cv.replaceWith(Object.assign(cover(this.meta.title, this.meta.id, true), { id: 'pl-cover' }));
    $('#pl-rate').textContent = `${String(this.rate).replace('.', ',')}x`;
    const sl = $('#pl-sleep');
    sl.replaceChildren(ic('moon', 18), this.sleep ? (this.sleep === 'chapter' ? 'Fim do cap.' : `${this.sleep} min`) : '');
    sl.setAttribute('aria-pressed', String(!!this.sleep));
    this.paintPlay();
  },
  paintPlay() {
    const playing = this.playing;
    const label = playing ? 'Pausar' : 'Reproduzir';
    for (const b of [$('#pl-play'), ...document.querySelectorAll('#pl-mob .play')]) {
      b.replaceChildren(ic(playing ? 'pause' : 'play', 24)); b.setAttribute('aria-label', label);
    }
  },
  tick() {
    const d = this.a.duration, t = this.a.currentTime;
    $('#pl-cur').textContent = fmtClock(t);
    $('#pl-dur').textContent = Number.isFinite(d) ? fmtClock(d) : '–:––';
    if (!this.dragging && Number.isFinite(d) && d > 0) {
      const v = (t / d) * 1000, s = $('#pl-scrub');
      s.value = v; s.style.background = `linear-gradient(to right, var(--accent) ${v / 10}%, var(--line) ${v / 10}%)`;
    }
    this.save();
    if (R.isOpen && R.data) R.tick();
  },
  session() {
    if (!('mediaSession' in navigator) || !this.meta) return;
    const c = this.chapter(this.idx);
    navigator.mediaSession.metadata = new MediaMetadata({ title: c ? c.title : '', artist: 'Audio-PDF', album: this.meta.title });
    const set = (n, f) => { try { navigator.mediaSession.setActionHandler(n, f); } catch { /* ação não suportada */ } };
    set('play', () => this.a.play()); set('pause', () => this.a.pause());
    set('seekbackward', () => this.skip(-30)); set('seekforward', () => this.skip(30));
    set('previoustrack', () => { const p = this.chapter(this.idx - 1); if (p) this.start(p.index, 0); });
    set('nexttrack', () => this.advance());
  },
};
(function wirePlayer() {
  const a = P.a;
  $('#pl-back').replaceChildren(ic('back', 26)); $('#pl-fwd').replaceChildren(ic('fwd', 26)); $('#pl-close').replaceChildren(ic('x', 18));
  $('#pl-back').onclick = () => P.skip(-30); $('#pl-fwd').onclick = () => P.skip(30);
  $('#pl-play').onclick = () => P.toggle();
  $('#pl-rate').onclick = () => P.cycleRate(); $('#pl-sleep').onclick = () => P.cycleSleep(); $('#pl-close').onclick = () => P.close();
  const mob = $('#pl-mob');
  mob.append(h('button', { class: 'btn icon ghost sm', 'aria-label': 'Voltar 30 segundos', onclick: () => P.skip(-30) }, ic('back', 24)),
    h('button', { class: 'play', style: 'width:44px;height:44px', onclick: () => P.toggle() }),
    h('button', { class: 'btn icon ghost sm', 'aria-label': 'Avançar 30 segundos', onclick: () => P.skip(30) }, ic('fwd', 24)));
  const sc = $('#pl-scrub');
  sc.addEventListener('pointerdown', () => (P.dragging = true));
  sc.addEventListener('input', () => {
    if (Number.isFinite(a.duration)) a.currentTime = (sc.value / 1000) * a.duration;
    sc.style.background = `linear-gradient(to right, var(--accent) ${sc.value / 10}%, var(--line) ${sc.value / 10}%)`;
  });
  sc.addEventListener('change', () => (P.dragging = false));
  a.addEventListener('timeupdate', () => P.tick());
  a.addEventListener('loadedmetadata', () => P.tick());
  a.addEventListener('play', () => { P.paintPlay(); P.emit(); P.schedule(); });
  a.addEventListener('pause', () => { P.paintPlay(); P.save(true); P.emit(); });
  a.addEventListener('ended', () => P.onEnded());
  a.addEventListener('error', () => { if (P.meta) toast('Não foi possível carregar o áudio.', 'err'); });
  new ResizeObserver(() => P.fit()).observe(P.bar);
  document.addEventListener('keydown', (e) => {
    if (!P.meta || e.metaKey || e.ctrlKey || e.altKey) return;
    const t = e.target;
    if (t.closest('input, textarea, select, dialog, [contenteditable]') || (t.closest('button, a, summary') && e.key === ' ')) return;
    if (e.key === ' ') { e.preventDefault(); P.toggle(); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); P.skip(-30); }
    else if (e.key === 'ArrowRight') { e.preventDefault(); P.skip(30); }
  });
  window.addEventListener('beforeunload', () => P.save(true));
})();

// ---------- leitor sincronizado: acompanha o PDF enquanto o áudio toca ----------
const R = {
  el: $('#reader'), isOpen: false, follow: true, tab: 'pdf', data: null, key: '', cur: -2, page: 1, loading: false,
  pageBox: null, textBox: null, pageLabel: null,
  toggle() { this.isOpen ? this.hide() : this.show(); },
  show() {
    if (!P.meta) { toast('Toque um capítulo primeiro.'); return; }
    this.isOpen = true; this.el.hidden = false; $('#pl-reader').setAttribute('aria-pressed', 'true');
    requestAnimationFrame(() => { this.el.classList.add('on'); document.body.classList.add('reader-open'); });
    this.sync(true);
  },
  hide() {
    this.isOpen = false; this.el.classList.remove('on'); document.body.classList.remove('reader-open');
    $('#pl-reader').setAttribute('aria-pressed', 'false');
    setTimeout(() => { if (!this.isOpen) this.el.hidden = true; }, 350);
  },
  chapterIdx() { return P.live && P.live.idx != null ? P.live.idx : P.idx; },
  async sync(force = false) {
    if (!this.isOpen || !P.meta) return;
    const idx = this.chapterIdx();
    if (!idx || idx < 1) return;
    const key = `${P.meta.id}:${idx}`;
    const stale = this.data && P.live && P.live.part >= this.data.timeline.length;
    if (!force && key === this.key && !stale) return;
    if (this.loading) return;
    this.loading = true;
    try {
      this.data = await api(`/api/books/${P.meta.id}/chapters/${idx}/sync`);
      this.key = key; this.cur = -2;
      this.render();
      this.tick(true);
    } catch (e) { toast(e.message, 'err'); } finally { this.loading = false; }
  },
  pIndex() {
    const tl = this.data.timeline;
    if (!tl.length || (P.live && P.live.part < 0)) return -2;
    if (P.live) return tl[Math.min(P.live.part, tl.length - 1)].p;
    const t = P.a.currentTime;
    let lo = 0, hi = tl.length - 1, i = 0;
    while (lo <= hi) { const m = (lo + hi) >> 1; if (tl[m].t <= t) { i = m; lo = m + 1; } else hi = m - 1; }
    return tl[i].p;
  },
  tick(force = false) {
    const p = this.pIndex();
    if (p === this.cur && !force) return;
    this.cur = p;
    const para = this.data.paragraphs[Math.max(p, 0)];
    const pg = para && para.rects[0] ? para.rects[0][0] : null;
    if (this.follow && pg && pg !== this.page) this.showPage(pg); else this.paintHl();
    for (const el of this.textBox ? this.textBox.children : []) el.classList.toggle('now', Number(el.dataset.i) === p);
    if (this.follow && this.tab === 'text' && p >= 0) this.textBox.children[p]?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  },
  seekPara(i) {
    const tl = this.data.timeline;
    const k = tl.findIndex((e) => e.p === i);
    if (k < 0) { toast('Esse trecho ainda não tem marcação de tempo.'); return; }
    if (P.live) { if (k < (P.chapter(P.live.idx)?.parts ?? 0)) P.startPart(P.live.idx, k); else toast('Esse trecho ainda está sendo convertido.'); return; }
    P.a.currentTime = tl[k].t + 0.01;
    P.a.play().catch(() => {});
  },
  showPage(n) {
    this.page = Math.max(1, Math.min(n, this.data.pages));
    if (!this.pageBox) return;
    const box = this.pageBox;
    const img = h('img', { alt: `Página ${this.page} do PDF`, src: `/api/books/${P.meta.id}/pages/${this.page}?w=1000` });
    img.addEventListener('load', () => box.style.setProperty('--ar', img.naturalWidth / img.naturalHeight));
    box.replaceChildren(img);
    this.data.paragraphs.forEach((para, i) => {
      for (const [pg, x0, y0, x1, y1] of para.rects) {
        if (pg !== this.page) continue;
        box.append(h('div', { class: 'hit', title: 'Ouvir a partir daqui', style: `left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%`, onclick: () => this.seekPara(i) }));
      }
    });
    if (this.pageLabel) this.pageLabel.textContent = `Página ${this.page} de ${this.data.pages}`;
    this.paintHl();
    if (this.page < this.data.pages) new Image().src = `/api/books/${P.meta.id}/pages/${this.page + 1}?w=1000`;
  },
  paintHl() {
    if (!this.pageBox) return;
    this.pageBox.querySelectorAll('.hl').forEach((e) => e.remove());
    const para = this.cur >= 0 ? this.data.paragraphs[this.cur] : null;
    for (const [pg, x0, y0, x1, y1] of para ? para.rects : []) {
      if (pg === this.page) this.pageBox.append(h('div', { class: 'hl', style: `left:${x0 * 100}%;top:${y0 * 100}%;width:${(x1 - x0) * 100}%;height:${(y1 - y0) * 100}%` }));
    }
  },
  render() {
    const d = this.data, c = P.chapter(this.chapterIdx());
    const tabBtn = (id, label) => h('button', { role: 'tab', 'aria-selected': String(this.tab === id), onclick: () => { this.tab = id; this.render(); this.tick(true); } }, label);
    const follow = h('button', { class: 'btn sm', 'aria-pressed': String(this.follow), title: 'Virar a página e rolar o texto sozinho', onclick: () => { this.follow = !this.follow; this.render(); this.tick(true); } }, this.follow ? 'Seguindo a leitura' : 'Seguir a leitura');
    const notes = [];
    if (d.approx) notes.push(h('span', { class: 'chip warn' }, 'Sincronia aproximada (áudio anterior à marcação)'));
    if (d.translated) notes.push(h('span', { class: 'chip idle' }, 'Texto traduzido; o PDF está no idioma original'));
    if (!d.paragraphs.some((p) => p.rects.length)) notes.push(h('span', { class: 'chip warn' }, 'Não foi possível localizar o texto no PDF'));
    this.pageBox = null; this.textBox = null; this.pageLabel = null;
    const body = h('div', { class: 'rd-body' });
    if (this.tab === 'pdf') {
      this.pageBox = h('div', { class: 'pg' });
      body.append(this.pageBox);
    } else {
      this.textBox = h('div', {}, d.paragraphs.map((p, i) => h('p', { class: 'rd-p', 'data-i': i, onclick: () => this.seekPara(i) }, p.text)));
      body.append(this.textBox);
    }
    const nav = this.tab === 'pdf' ? (() => {
      this.pageLabel = h('span', { class: 'num grow' }, `Página ${this.page} de ${d.pages}`);
      return h('div', { class: 'rd-sub' },
        h('button', { class: 'btn icon sm', 'aria-label': 'Página anterior', onclick: () => { this.follow = false; this.showPage(this.page - 1); this.render(); this.tick(true); } }, ic('chevl', 18)),
        this.pageLabel,
        h('button', { class: 'btn icon sm', 'aria-label': 'Próxima página', onclick: () => { this.follow = false; this.showPage(this.page + 1); this.render(); this.tick(true); } }, ic('chevr', 18)));
    })() : null;
    this.el.replaceChildren(
      h('div', { class: 'rd-head' }, h('h2', {}, c ? `Cap. ${c.index} · ${c.title}` : 'Acompanhar leitura'),
        h('div', { class: 'tabs', role: 'tablist' }, tabBtn('pdf', 'PDF'), tabBtn('text', 'Texto')), follow,
        h('button', { class: 'btn icon sm ghost', 'aria-label': 'Fechar leitor', onclick: () => this.hide() }, ic('x', 18))),
      ...(notes.length ? [h('div', { class: 'rd-sub' }, ...notes)] : []), ...(nav ? [nav] : []), body);
    if (this.tab === 'pdf') this.showPage(this.page);
  },
};
$('#pl-reader').replaceChildren(ic('book', 18), 'Acompanhar');
$('#pl-reader').onclick = () => R.toggle();
P.subs.add(() => R.sync());
document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && R.isOpen && !e.target.closest('dialog')) R.hide(); });

// ---------- roteador ----------
let cleanup = null;
function setNav(w) {
  for (const [id, k] of [['nav-lib', 'lib'], ['nav-new', 'new'], ['nav-users', 'users']]) {
    const el = $(`#${id}`);
    if (!el) continue;
    if (k === w) el.setAttribute('aria-current', 'page'); else el.removeAttribute('aria-current');
  }
}
const heading = (title, sub, ...right) => h('div', { class: 'page-head' }, h('div', {}, h('h1', {}, title), sub ? h('p', { class: 'sub' }, sub) : null), ...right);

// ---------- biblioteca ----------
async function viewLibrary() {
  setNav('lib'); document.title = 'Biblioteca · Audio-PDF';
  $app.replaceChildren(heading('Sua biblioteca'), h('div', { class: 'grid' }, [0, 1, 2, 3].map(() => h('div', { class: 'skeleton', style: 'aspect-ratio:2/3' }))));
  const books = await api('/api/books');
  const newBtn = h('a', { class: 'btn primary', href: '#/new' }, ic('plus', 18), 'Novo audiobook');
  if (!books.length) {
    $app.replaceChildren(heading('Sua biblioteca', null, newBtn),
      h('div', { class: 'empty card' }, ic('upload', 36), h('div', {}, h('h2', {}, 'Nenhum audiobook ainda'), h('p', { class: 'sub' }, 'Envie um PDF e escolha a voz. Você pode ouvir enquanto converte.')), newBtn));
    return;
  }
  const total = books.reduce((a, b) => a + b.duration, 0);
  const parts = [heading('Sua biblioteca', `${books.length} ${books.length === 1 ? 'livro' : 'livros'}${total ? ` · ${fmtDur(total)} de áudio pronto` : ''}`, newBtn)];
  const last = store.get('last');
  if (last && books.some((b) => b.id === last.b)) {
    try {
      const m = await api(`/api/books/${last.b}`);
      const c = m.chapters.find((x) => x.index === last.i);
      if (c && c.status === 'done') {
        parts.push(h('div', { class: 'resume' }, cover(m.title, m.id, true),
          h('div', { class: 'grow' }, h('h3', {}, 'Continuar ouvindo'), h('div', { class: 'muted' }, `${m.title} · cap. ${c.index} · ${fmtClock(last.t)}`)),
          h('button', { class: 'btn primary icon', 'aria-label': `Continuar ${c.title}`, onclick: () => { P.meta = m; P.start(c.index, last.t); } }, ic('play', 22))));
      }
    } catch { /* ignorar */ }
  }
  parts.push(h('div', { class: 'grid' }, books.map((b) => {
    const pct = b.chapter_count ? Math.round((b.done / b.chapter_count) * 100) : 0;
    const st = b.failed ? h('span', { class: 'chip fail' }, `${b.failed} com falha`)
      : b.running ? h('span', { class: 'chip run' }, 'Convertendo')
      : b.done === b.chapter_count ? h('span', { class: 'chip' }, 'Pronto')
      : h('span', { class: 'chip idle' }, b.done ? 'Parcial' : 'Não convertido');
    return h('a', { class: 'book', href: `#/book/${b.id}` }, cover(b.title, b.id),
      h('div', {}, h('h3', {}, b.title), h('div', { class: 'muted num', style: 'font-size:13px;margin:2px 0 8px' }, `${b.done} de ${b.chapter_count} capítulos${b.duration ? ` · ${fmtDur(b.duration)}` : ''}`),
        h('div', { class: 'bar', role: 'progressbar', 'aria-label': 'Capítulos prontos', 'aria-valuenow': pct, 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('i', { style: `width:${pct}%` })),
        h('div', { style: 'margin-top:8px' }, st)));
  })));
  $app.replaceChildren(...parts);
}

// ---------- novo audiobook ----------
function uploadFile(file, onProgress) {
  return new Promise((resolve, reject) => {
    const x = new XMLHttpRequest();
    x.open('POST', '/api/books');
    x.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total);
    x.onload = () => {
      let d = null; try { d = JSON.parse(x.responseText); } catch { /* corpo não JSON */ }
      x.status >= 200 && x.status < 300 ? resolve(d) : reject(new Error((d && d.detail) || x.statusText || 'Falha no envio'));
    };
    x.onerror = () => reject(new Error('Falha de rede ao enviar o arquivo'));
    const fd = new FormData(); fd.append('file', file); x.send(fd);
  });
}
async function viewNew() {
  setNav('new'); document.title = 'Novo audiobook · Audio-PDF';
  const err = h('div', { class: 'notice err', role: 'alert', hidden: true });
  const showErr = (m) => { err.hidden = !m; err.replaceChildren(ic('alert', 18), m || ''); };
  const input = h('input', { type: 'file', accept: 'application/pdf', id: 'pdf', class: 'sr' });
  const rights = h('input', { type: 'checkbox', id: 'rights' });
  const zone = h('label', { class: 'drop', for: 'pdf' });
  let pending = null; // arquivo escolhido antes de confirmar os direitos
  rights.addEventListener('change', () => { if (rights.checked && pending) send(pending); });
  const idle = () => zone.replaceChildren(ic('upload', 36), h('strong', {}, 'Arraste o PDF aqui'), h('span', { class: 'muted' }, 'ou clique para escolher · até 200 MB'));
  idle();
  async function send(file) {
    showErr('');
    if (!file) return;
    if (!rights.checked) { pending = file; showErr('Confirme abaixo que você tem direito sobre este conteúdo. O envio começa em seguida.'); rights.focus(); return; }
    pending = null;
    if (file.type && file.type !== 'application/pdf') { showErr('Envie um arquivo PDF.'); return; }
    const bar = h('i', { style: 'width:0%' });
    const status = h('span', { class: 'muted num' }, 'Enviando… 0%');
    zone.replaceChildren(h('strong', {}, file.name), h('div', { class: 'progress-line' }, h('div', { class: 'bar run', role: 'progressbar', 'aria-label': 'Envio' }, bar), status));
    try {
      const meta = await uploadFile(file, (f) => {
        bar.style.width = `${Math.round(f * 100)}%`;
        status.textContent = f < 1 ? `Enviando… ${Math.round(f * 100)}%` : 'Analisando capítulos e idioma…';
      });
      renderConfigure(meta, { isNew: true });
    } catch (e) { showErr(e.message); idle(); input.value = ''; }
  }
  input.addEventListener('change', () => send(input.files[0]));
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', (e) => { e.preventDefault(); zone.classList.remove('over'); send(e.dataTransfer.files[0]); });
  $app.replaceChildren(heading('Novo audiobook', 'Envie o PDF. Depois você escolhe capítulos, idioma e voz.'), err, input, zone,
    h('label', { class: 'hint', style: 'display:flex;gap:10px;align-items:flex-start' }, rights, 'Confirmo que tenho direito sobre este conteúdo e que o áudio é para uso pessoal.'));
}

// ---------- configurar conversão (livro novo ou mais capítulos) ----------
async function renderConfigure(meta, { isNew }) {
  setNav(isNew ? 'new' : 'lib'); document.title = `Converter · ${meta.title}`;
  const [allVoices, langs, translators] = await Promise.all([api('/api/voices'), api('/api/languages'), api('/api/translators')]);
  const saved = meta.settings || {};
  const srcLang = langs.find((l) => l.base === meta.language);
  let target = saved.lang && langs.some((l) => l.code === saved.lang) ? saved.lang : (srcLang || langs[0]).code;
  const voicesFor = (code) => allVoices.filter((v) => v.lang === code);
  let voice = (voicesFor(target).find((v) => v.id === saved.voice) || voicesFor(target)[0]).id;
  let speed = saved.speed || 1;
  let translator = translators.includes(saved.translator) ? saved.translator : translators[0];
  const picked = new Set(meta.chapters.filter((c) => isNew || c.status !== 'done').map((c) => c.index));
  const rows = new Map();

  // --- painel de ajustes
  const sample = new Audio();
  const voiceBox = h('div', { style: 'display:flex;flex-direction:column;gap:8px' });
  const note = h('span', { class: 'hint' });
  const trSel = h('select', { id: 'tr', name: 'translator', onchange: (e) => { translator = e.target.value; update(); } },
    translators.map((t) => h('option', { value: t, selected: t === translator }, { argos: 'Argos (local, gratuito)', deepl: 'DeepL (API)', claude: 'Claude (API)' }[t] || t)));
  const trField = h('label', { class: 'field', for: 'tr' }, 'Tradutor', trSel);
  const translating = () => !(srcLang && srcLang.code === target);
  function renderVoices() {
    const vs = voicesFor(target);
    if (!vs.some((v) => v.id === voice)) voice = vs[0].id;
    voiceBox.replaceChildren(...vs.map((v) => {
      const btn = h('button', { type: 'button', class: 'btn icon sm', 'aria-label': `Ouvir amostra de ${v.label}`, onclick: (e) => {
        e.preventDefault();
        sample.pause(); sample.src = `/api/voices/${v.id}/sample`;
        btn.replaceChildren(h('span', { class: 'muted', style: 'font-size:12px' }, '…'));
        sample.play().then(() => btn.replaceChildren(ic('play', 16))).catch(() => { btn.replaceChildren(ic('play', 16)); toast('Não foi possível tocar a amostra.', 'err'); });
      } }, ic('play', 16));
      return h('label', { class: 'voice' }, h('input', { type: 'radio', name: 'voice', value: v.id, checked: v.id === voice, onchange: () => { voice = v.id; update(); } }),
        h('span', { class: 't' }, h('b', {}, v.label), h('span', { class: 'muted' }, ` · ${v.gender} · ${v.lang}`)), btn);
    }));
  }
  const langSel = h('select', { id: 'lang', name: 'lang', onchange: (e) => { target = e.target.value; renderVoices(); update(); } },
    langs.map((l) => h('option', { value: l.code, selected: l.code === target }, l.name)));
  const speedLbl = h('span', { class: 'num', style: 'color:var(--accent);font-weight:600' }, '1x');
  const speedIn = h('input', { type: 'range', id: 'speed', min: 0.75, max: 1.5, step: 0.05, value: speed, oninput: (e) => { speed = parseFloat(e.target.value); update(); } });

  // --- capítulos
  const list = h('div', { class: 'chapters', role: 'list' });
  for (const c of meta.chapters) {
    const cb = h('input', { type: 'checkbox', checked: picked.has(c.index), 'aria-label': `Capítulo ${c.index}: ${c.title}`, onchange: () => { cb.checked ? picked.add(c.index) : picked.delete(c.index); update(); } });
    const row = h('label', { class: 'crow', role: 'listitem' }, cb, h('span', { class: 'n num' }, c.index), h('span', { class: 't', title: c.title }, c.title),
      c.status !== 'idle' ? chip(c.status) : null, h('span', { class: 'm num' }, `${fmtDur(c.chars / CHARS_PER_SEC)}`));
    rows.set(c.index, { row, cb, c });
    list.append(row);
  }
  const setAll = (fn) => { for (const { cb, c } of rows.values()) { cb.checked = fn(c); cb.checked ? picked.add(c.index) : picked.delete(c.index); } update(); };
  const search = h('input', { type: 'search', placeholder: 'Filtrar capítulos…', 'aria-label': 'Filtrar capítulos', oninput: (e) => {
    const q = e.target.value.trim().toLowerCase();
    for (const { row, c } of rows.values()) row.hidden = !!q && !(`${c.index} ${c.title}`.toLowerCase().includes(q));
  } });

  // --- barra de ação
  const stats = h('div', { class: 'stats' });
  const warn = h('div', { style: 'display:flex;flex-direction:column;gap:8px' });
  const go = h('button', { class: 'btn primary', onclick: async () => {
    go.disabled = true;
    try {
      await post(`/api/books/${meta.id}/jobs`, { chapters: [...picked].sort((a, b) => a - b), voice, speed, target_language: target, translator });
      toast('Conversão iniciada. Você já pode ouvir os primeiros trechos.');
      location.hash = `#/book/${meta.id}`;
    } catch (e) { toast(e.message, 'err'); go.disabled = false; }
  } });
  function update() {
    const sel = meta.chapters.filter((c) => picked.has(c.index));
    const chars = sel.reduce((a, c) => a + c.chars, 0), audio = chars / CHARS_PER_SEC / speed;
    stats.replaceChildren(
      h('div', {}, h('b', { class: 'num' }, sel.length), h('span', {}, 'capítulos')),
      h('div', {}, h('b', { class: 'num' }, audio ? fmtDur(audio) : '—'), h('span', {}, 'de áudio')),
      h('div', {}, h('b', { class: 'num' }, audio ? `≈ ${fmtDur(audio / PROCESS_FACTOR)}` : '—'), h('span', {}, 'para converter (varia com o hardware)')));
    go.disabled = sel.length === 0;
    go.replaceChildren(ic('play', 18), sel.length ? `Converter ${sel.length} ${sel.length === 1 ? 'capítulo' : 'capítulos'}` : 'Selecione capítulos');
    speedLbl.textContent = `${speed.toFixed(2).replace(/\.?0+$/, '').replace('.', ',')}x`;
    trField.hidden = !translating() || translators.length < 2;
    const from = srcLang ? srcLang.name : (meta.language || 'idioma não identificado');
    note.textContent = translating() ? `Idioma do livro: ${from}. O texto será traduzido antes de narrar.` : `Idioma do livro: ${from}. Sem tradução.`;
    const redo = sel.filter((c) => c.status === 'done' && (c.lang !== target || c.voice !== voice)).length;
    warn.replaceChildren(
      ...(redo ? [h('div', { class: 'notice' }, ic('alert', 18), `${redo} capítulo(s) já prontos serão refeitos com a nova voz ou idioma.`)] : []));
  }

  const notices = [];
  if (meta.ocr_pages) notices.push(h('div', { class: 'notice info' }, ic('info', 18), `${meta.ocr_pages} página(s) escaneadas foram lidas por OCR. Pode haver erros de leitura; ouça uma amostra antes de converter tudo.`));
  if (meta.scanned_pages) notices.push(h('div', { class: 'notice' }, ic('alert', 18), `${meta.scanned_pages} página(s) sem texto legível foram ignoradas.`));
  renderVoices();
  const info = [`${meta.pages} páginas`, `${meta.chapters.length} capítulos`, srcLang ? srcLang.name : null].filter(Boolean).join(' · ');
  $app.replaceChildren(
    heading(isNew ? meta.title : `Converter · ${meta.title}`, info,
      isNew ? null : h('a', { class: 'btn', href: `#/book/${meta.id}` }, 'Cancelar')),
    ...notices,
    h('div', { class: 'cols' },
      h('section', { class: 'card', 'aria-label': 'Capítulos' },
        h('div', { class: 'toolbar' }, h('h2', { class: 'grow' }, 'Capítulos'),
          h('button', { class: 'btn sm', onclick: () => setAll(() => true) }, 'Todos'),
          h('button', { class: 'btn sm', onclick: () => setAll(() => false) }, 'Nenhum'),
          h('button', { class: 'btn sm', onclick: () => setAll((c) => c.status !== 'done') }, 'Só os não prontos')),
        search, list),
      h('section', { class: 'card', 'aria-label': 'Ajustes' },
        h('h2', {}, 'Idioma, voz e velocidade'),
        h('label', { class: 'field', for: 'lang' }, 'Idioma de saída', langSel, note), trField,
        h('fieldset', { style: 'border:0;padding:0;margin:0' }, h('legend', { style: 'font-weight:500;margin-bottom:8px;padding:0' }, 'Voz'), voiceBox),
        h('label', { class: 'field', for: 'speed' }, h('span', { style: 'display:flex;justify-content:space-between' }, 'Velocidade da narração', speedLbl), speedIn),
        warn)),
    h('div', { class: 'actionbar' }, stats, go));
  update();
  cleanup = () => sample.pause();
}
async function viewConvert(id) {
  $app.replaceChildren(h('div', { class: 'skeleton', style: 'height:240px' }));
  renderConfigure(await api(`/api/books/${id}`), { isNew: false });
}

// ---------- livro ----------
async function viewBook(id) {
  setNav('lib');
  let meta = await api(`/api/books/${id}`);
  const caps = await api('/api/capabilities').catch(() => ({ llm: false }));
  document.title = `${meta.title} · Audio-PDF`;
  let q = '', timer = null, alive = true;
  P.setMeta(meta);
  const head = h('div', { class: 'book-head' });
  const tl = h('div', { class: 'timeline', role: 'group', 'aria-label': 'Capítulos do livro' });
  const legend = h('div', { class: 'legend' });
  const list = h('div', { class: 'chapters', style: 'max-height:none;overflow:visible', role: 'list' });
  const actionsBox = h('div', { class: 'actions' });
  const search = h('input', { type: 'search', placeholder: 'Filtrar capítulos…', 'aria-label': 'Filtrar capítulos', oninput: (e) => { q = e.target.value.trim().toLowerCase(); paintList(); } });
  const playing = (c) => P.meta && P.meta.id === id && P.idx === c.index;

  function paintHead() {
    if (head.querySelector('details[open]')) return;
    const done = meta.chapters.filter((c) => c.status === 'done');
    const dur = done.reduce((a, c) => a + (c.duration || 0), 0), busy = metaBusy(meta);
    const s = meta.settings;
    const voiceLabel = s ? ` · voz ${s.voice.replace(/^[a-z]{2}_/, '').replace(/^./, (x) => x.toUpperCase())} · ${String(s.speed).replace('.', ',')}x` : '';
    head.replaceChildren(cover(meta.title, meta.id),
      h('div', {}, h('h1', {}, meta.title),
        h('p', { class: 'sub num' }, `${meta.pages} páginas · ${done.length} de ${meta.chapters.length} capítulos prontos${dur ? ` · ${fmtDur(dur)}` : ''}${voiceLabel}`),
        actionsBox));
    actionsBox.replaceChildren(
      done.length ? h('a', { class: 'btn primary', href: `/api/books/${id}/download`, download: '' }, ic('download', 18), `Baixar prontos (${done.length})`)
        : h('span', { class: 'btn', 'aria-disabled': 'true' }, ic('download', 18), 'Baixar prontos'),
      h('a', { class: 'btn', href: `#/convert/${id}` }, ic('plus', 18), 'Converter capítulos'),
      ...(busy ? [h('button', { class: 'btn danger', onclick: async () => { await post(`/api/books/${id}/cancel`); toast('Cancelando…'); refresh(); } }, 'Cancelar conversão')] : []),
      h('details', { class: 'menu' }, h('summary', { class: 'btn icon', 'aria-label': 'Mais ações' }, ic('more', 20)),
        h('div', { class: 'pop' },
          h('button', { onclick: reanalyze }, ic('refresh', 18), 'Reanalisar texto do PDF'),
          h('button', { class: 'danger', onclick: remove }, ic('trash', 18), 'Excluir livro'))));
  }
  function paintTimeline() {
    tl.replaceChildren(...meta.chapters.map((c) => {
      const k = c.status === 'done' ? 'done' : isBusy(c) ? 'run' : c.status === 'failed' ? 'fail' : '';
      return h('button', { class: `${k} ${playing(c) ? 'cur' : ''}`, style: `flex-grow:${Math.max(c.chars, 1)}`, title: `${c.index}. ${c.title} · ${STATUS[c.status][0]}`,
        'aria-label': `Capítulo ${c.index}: ${c.title}, ${STATUS[c.status][0]}`, onclick: () => (playable(c) ? P.open(id, c.index) : toast(`Capítulo ${c.index}: ${STATUS[c.status][0].toLowerCase()}.`)) });
    }));
    const n = (f) => meta.chapters.filter(f).length;
    legend.replaceChildren(
      h('span', {}, h('i', { style: 'background:var(--accent)' }), `${n((c) => c.status === 'done')} prontos`),
      h('span', {}, h('i', { style: 'background:var(--run)' }), `${n(isBusy)} em andamento`),
      h('span', {}, h('i', { style: 'background:var(--err)' }), `${n((c) => c.status === 'failed')} com falha`),
      h('span', {}, h('i', { style: 'background:var(--line)' }), `${n((c) => c.status === 'idle' || c.status === 'canceled')} sem áudio`),
      h('span', {}, 'A largura de cada trecho é proporcional ao tamanho do capítulo.'));
  }
  function paintList() {
    if (list.querySelector('details[open]')) return; // não fecha o menu aberto a cada atualização
    const shown = meta.chapters.filter((c) => !q || `${c.index} ${c.title}`.toLowerCase().includes(q));
    if (!shown.length) { list.replaceChildren(h('div', { class: 'empty' }, 'Nenhum capítulo com esse filtro.')); return; }
    list.replaceChildren(...shown.map((c) => {
      const now = playing(c), can = playable(c);
      const play = h('button', { class: 'btn icon sm ghost', 'aria-label': now && P.playing ? `Pausar capítulo ${c.index}` : `Ouvir capítulo ${c.index}`, disabled: !can,
        onclick: () => (now ? P.toggle() : P.open(id, c.index)) }, ic(now && P.playing ? 'pause' : 'play', 18));
      return h('div', { class: `brow ${now ? 'now' : ''}`, role: 'listitem' },
        h('span', { class: 'num muted', style: 'text-align:right' }, c.index),
        h('div', { class: 't' }, h('a', { href: '#', title: c.title, onclick: (e) => { e.preventDefault(); can ? (now ? P.toggle() : P.open(id, c.index)) : toast('Esse capítulo ainda não foi convertido.'); } }, c.title),
          c.status === 'running' || c.status === 'translating'
            ? h('div', { class: 'bar run', style: 'margin-top:6px', role: 'progressbar', 'aria-label': `Progresso do capítulo ${c.index}`, 'aria-valuenow': Math.round(c.progress * 100), 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('i', { style: `width:${c.progress * 100}%` })) : null,
          c.error ? h('div', { class: 'err' }, c.error) : null,
          ...videoLines(c)),
        h('span', { class: 'dur muted num', style: 'font-size:13px' }, c.duration ? fmtClock(c.duration) : ''),
        h('div', { class: 'acts' },
          c.status !== 'done' ? chip(c.status) : null,
          play,
          c.status === 'done' ? h('a', { class: 'btn icon sm ghost', href: `/api/books/${id}/audio/${c.index}?download=1`, download: '', 'aria-label': `Baixar capítulo ${c.index}` }, ic('download', 18)) : null,
          c.status === 'done' ? videoMenu(c) : null,
          c.status === 'failed' || c.status === 'canceled'
            ? h('button', { class: 'btn icon sm ghost', 'aria-label': `Reprocessar capítulo ${c.index}`, onclick: () => retry(c) }, ic('refresh', 18)) : null));
    }));
  }
  const paintAll = () => { paintHead(); paintTimeline(); paintList(); };
  const KIND = { leitura: 'vídeo da leitura', resumo: 'vídeo resumo', aula: 'vídeo-aula com IA', aula_simples: 'vídeo-aula econômica' };
  const KIND_HINT = { leitura: 'O PDF acompanhado, com o trecho lido em destaque', resumo: 'Só os trechos principais do capítulo, narrados (seleção automática, sem reescrever)', aula: 'Aula educacional escrita por IA: tópicos, explicação, resumo e perguntas. Tem custo no provedor de LLM e envia o texto do capítulo a ele.', aula_simples: 'Mesmo formato da aula, sem IA e sem custo: usa as frases mais representativas e perguntas de completar. Não reescreve nem explica.' };
  function videoLines(c) {
    return Object.entries(c.videos || {}).filter(([, v]) => v.status === 'queued' || v.status === 'running').map(([k, v]) =>
      h('div', { class: 'hint', style: 'margin-top:6px' }, `Gerando ${KIND[k]}… ${Math.round((v.progress || 0) * 100)}%`,
        h('div', { class: 'bar run', style: 'margin-top:4px', role: 'progressbar', 'aria-label': `Progresso do ${KIND[k]}`, 'aria-valuenow': Math.round((v.progress || 0) * 100), 'aria-valuemin': 0, 'aria-valuemax': 100 }, h('i', { style: `width:${(v.progress || 0) * 100}%` }))));
  }
  async function requestVideo(idx, kind) {
    try { await post(`/api/books/${id}/chapters/${idx}/video`, { kind }); toast(`Gerando ${KIND[kind]}. Você acompanha o progresso na lista.`); refresh(); } catch (e) { toast(e.message, 'err'); }
  }
  async function removeVideo(idx, kind) {
    if (!await confirmDialog({ title: 'Excluir o vídeo?', body: 'O arquivo será apagado. Dá para gerar de novo depois.', ok: 'Excluir', danger: true })) return;
    try { await api(`/api/books/${id}/chapters/${idx}/video/${kind}`, { method: 'DELETE' }); refresh(); } catch (e) { toast(e.message, 'err'); }
  }
  function watchVideo(c, kind) {
    P.a.pause();
    const url = `/api/books/${id}/chapters/${c.index}/video/${kind}`;
    const vid = h('video', { controls: true, autoplay: true, playsinline: true, src: url, style: 'width:100%;border-radius:8px;background:#000' });
    const dlg = h('dialog', { style: 'width:min(960px,94vw)', 'aria-label': `Vídeo do capítulo ${c.index}` },
      h('div', { style: 'display:flex;align-items:center;gap:8px;margin-bottom:12px' }, h('h2', { style: 'flex:1;min-width:0' }, `Cap. ${c.index} · ${KIND[kind]}`),
        h('a', { class: 'btn sm', href: `${url}?download=1`, download: '' }, ic('download', 16), 'Baixar'),
        h('button', { class: 'btn icon sm ghost', 'aria-label': 'Fechar', onclick: () => dlg.close() }, ic('x', 18))), vid);
    dlg.addEventListener('close', () => { vid.pause(); vid.removeAttribute('src'); dlg.remove(); });
    document.body.append(dlg); dlg.showModal();
  }
  function videoMenu(c) {
    const close = (e) => e.currentTarget.closest('details').removeAttribute('open');
    const items = [];
    for (const kind of ['leitura', 'resumo', 'aula_simples', 'aula']) {
      const v = (c.videos || {})[kind];
      if (v && (v.status === 'queued' || v.status === 'running')) {
        items.push(h('div', { class: 'hint', style: 'padding:8px 12px' }, `Gerando ${KIND[kind]}… ${Math.round((v.progress || 0) * 100)}%`));
      } else if (v && v.status === 'done') {
        items.push(h('button', { onclick: (e) => { close(e); watchVideo(c, kind); } }, ic('play', 18), `Assistir ${KIND[kind]}`),
          h('a', { href: `/api/books/${id}/chapters/${c.index}/video/${kind}?download=1`, download: '' }, ic('download', 18), `Baixar ${KIND[kind]}`),
          h('button', { class: 'danger', onclick: (e) => { close(e); removeVideo(c.index, kind); } }, ic('trash', 18), `Excluir ${KIND[kind]}`));
      } else if (kind === 'aula' && !caps.llm) {
        items.push(h('div', { class: 'hint', style: 'padding:8px 12px' }, 'Vídeo-aula indisponível: configure OPENCODE_API_KEY (ou LLM_API_KEY) no .env e reinicie o servidor.'));
        continue;
      } else {
        if (v && v.error) items.push(h('div', { class: 'err hint', style: 'padding:8px 12px;color:var(--err)' }, v.error));
        items.push(h('button', { title: KIND_HINT[kind], onclick: (e) => { close(e); requestVideo(c.index, kind); } }, ic('video', 18), `${v ? 'Tentar de novo: ' : 'Gerar '}${KIND[kind]}`));
      }
      const est = kind === 'aula' ? ` Estimativa: ~${Math.max(1, Math.round(Math.min(c.chars, caps.budget_chars || 20000) / 3500))} mil tokens de entrada.` : '';
      items.push(h('div', { class: 'hint', style: 'padding:0 12px 6px' }, KIND_HINT[kind] + est));
    }
    return h('details', { class: 'menu' }, h('summary', { class: 'btn icon sm ghost', 'aria-label': `Vídeos do capítulo ${c.index}`, title: 'Vídeos do capítulo' }, ic('video', 18)),
      h('div', { class: 'pop', style: 'min-width:280px' }, ...items));
  }
  async function retry(c) {
    const s = meta.settings || { voice: 'pf_dora', speed: 1, lang: 'pt-BR' };
    try { await post(`/api/books/${id}/jobs`, { chapters: [c.index], voice: c.voice || s.voice, speed: c.speed || s.speed, target_language: c.lang || s.lang, translator: s.translator }); refresh(); } catch (e) { toast(e.message, 'err'); }
  }
  async function reanalyze() {
    document.querySelector('.menu')?.removeAttribute('open');
    if (!await confirmDialog({ title: 'Reanalisar o texto?', body: 'O texto é extraído de novo do PDF original. Capítulos prontos mantêm o áudio; os demais usarão o texto novo.', ok: 'Reanalisar' })) return;
    try { meta = await post(`/api/books/${id}/reanalyze`); toast('Texto reanalisado.'); paintAll(); } catch (e) { toast(e.message, 'err'); }
  }
  async function remove() {
    document.querySelector('.menu')?.removeAttribute('open');
    if (!await confirmDialog({ title: 'Excluir este livro?', body: 'O PDF, o texto e todos os áudios serão apagados. Isso não pode ser desfeito.', ok: 'Excluir', danger: true })) return;
    try { if (P.meta && P.meta.id === id) P.close(); await api(`/api/books/${id}`, { method: 'DELETE' }); store.set('last', null); toast('Livro excluído.'); location.hash = '#/'; } catch (e) { toast(e.message, 'err'); }
  }
  async function refresh() {
    if (!alive) return;
    try { meta = await api(`/api/books/${id}`); } catch { location.hash = '#/'; return; }
    P.setMeta(meta); paintAll();
    clearTimeout(timer);
    if (metaBusy(meta)) timer = setTimeout(refresh, 2000);
  }
  const onPlayer = () => { if (alive) { paintTimeline(); paintList(); } };
  P.subs.add(onPlayer);
  cleanup = () => { alive = false; clearTimeout(timer); P.subs.delete(onPlayer); };

  $app.replaceChildren(head, h('section', { 'aria-label': 'Linha do tempo do livro', style: 'display:flex;flex-direction:column;gap:10px' }, tl, legend),
    h('section', { class: 'card', 'aria-label': 'Capítulos' }, h('div', { class: 'toolbar' }, h('h2', { class: 'grow' }, 'Capítulos'), h('div', { style: 'width:min(280px,100%)' }, search)), list));
  paintAll();
  if (metaBusy(meta)) timer = setTimeout(refresh, 2000);
}

// ---------- sessão e usuários ----------
const session = { user: null };
function renderUserbar() {
  const u = session.user;
  document.body.classList.toggle('anon', !u);
  $('#userbar').replaceChildren(...(u ? [
    h('span', { class: 'muted who' }, u.name),
    u.role === 'admin' ? h('a', { class: 'btn ghost sm', href: '#/users', id: 'nav-users' }, ic('user', 18), 'Usuários') : null,
    h('button', { class: 'btn ghost sm', onclick: changePasswordDialog }, 'Senha'),
    h('button', { class: 'btn ghost sm', onclick: logout }, ic('out', 18), 'Sair'),
  ] : []));
}
async function logout() {
  try { await post('/api/auth/logout'); } catch { /* sessão já expirada */ }
  location.hash = '#/'; location.reload();
}
function formDialog({ title, fields, ok = 'Salvar', onSubmit }) {
  return new Promise((resolve) => {
    const err = h('div', { class: 'notice err', role: 'alert', hidden: true });
    const els = {};
    const rows = fields.map((f) => {
      const id = `f-${f.key}`;
      if (f.type === 'checkbox') {
        els[f.key] = h('input', { type: 'checkbox', id, checked: !!f.value });
        return h('label', { class: 'check' }, els[f.key], f.label);
      }
      els[f.key] = f.type === 'select'
        ? h('select', { id }, f.options.map(([v, l]) => h('option', { value: v, selected: v === f.value }, l)))
        : h('input', { type: f.type || 'text', id, value: f.value ?? '', autocomplete: f.autocomplete || 'off', required: f.required, minlength: f.minlength });
      return h('label', { class: 'field', for: id }, f.label, els[f.key], f.hint ? h('span', { class: 'hint' }, f.hint) : null);
    });
    const submit = h('button', { class: 'btn primary', type: 'submit' }, ok);
    const dlg = h('dialog', { 'aria-label': title },
      h('form', { class: 'stack', onsubmit: async (e) => {
        e.preventDefault();
        const vals = Object.fromEntries(fields.map((f) => [f.key, f.type === 'checkbox' ? els[f.key].checked : els[f.key].value]));
        submit.disabled = true; err.hidden = true;
        try { await onSubmit(vals); dlg.close('yes'); } catch (x) { err.hidden = false; err.replaceChildren(ic('alert', 18), x.message); submit.disabled = false; }
      } }, h('h2', {}, title), err, ...rows,
      h('div', { class: 'row' }, h('button', { class: 'btn', type: 'button', onclick: () => dlg.close('no') }, 'Cancelar'), submit)));
    dlg.addEventListener('close', () => { resolve(dlg.returnValue === 'yes'); dlg.remove(); });
    document.body.append(dlg); dlg.showModal();
  });
}
const changePasswordDialog = () => formDialog({
  title: 'Trocar a minha senha', ok: 'Trocar',
  fields: [
    { key: 'current', label: 'Senha atual', type: 'password', required: true, autocomplete: 'current-password' },
    { key: 'new', label: 'Nova senha', type: 'password', required: true, minlength: 8, autocomplete: 'new-password', hint: 'De 8 a 128 caracteres. Os outros dispositivos serão desconectados.' },
  ],
  onSubmit: async (v) => { await post('/api/auth/password', v); toast('Senha alterada.'); },
});
function viewLogin() {
  document.title = 'Entrar · Audio-PDF';
  const err = h('div', { class: 'notice err', role: 'alert', hidden: true });
  const email = h('input', { type: 'email', id: 'lg-email', required: true, autocomplete: 'username' });
  const pass = h('input', { type: 'password', id: 'lg-pass', required: true, autocomplete: 'current-password' });
  const btn = h('button', { class: 'btn primary', type: 'submit' }, 'Entrar');
  $app.replaceChildren(h('form', { class: 'card login', onsubmit: async (e) => {
    e.preventDefault(); btn.disabled = true; err.hidden = true;
    try {
      session.user = await post('/api/auth/login', { email: email.value, password: pass.value });
      renderUserbar(); route();
    } catch (x) { err.hidden = false; err.replaceChildren(ic('alert', 18), x.message); btn.disabled = false; pass.select(); }
  } }, h('div', {}, h('h1', {}, 'Entrar'), h('p', { class: 'sub' }, 'Use a conta criada pelo administrador.')), err,
  h('label', { class: 'field', for: 'lg-email' }, 'E-mail', email), h('label', { class: 'field', for: 'lg-pass' }, 'Senha', pass), btn));
  email.focus();
}
const fmtWhen = (t) => (t ? new Date(t * 1000).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' }) : 'nunca');
async function viewUsers() {
  if (session.user.role !== 'admin') { location.hash = '#/'; return; }
  setNav('users'); document.title = 'Usuários · Audio-PDF';
  const body = h('tbody');
  const load = async () => {
    const users = await api('/api/users');
    body.replaceChildren(...users.map((u) => h('tr', {},
      h('td', {}, h('strong', {}, u.name), h('div', { class: 'hint' }, u.email)),
      h('td', {}, h('span', { class: `chip ${u.role === 'admin' ? '' : 'idle'}` }, u.role === 'admin' ? 'Administrador' : 'Usuário')),
      h('td', {}, h('span', { class: `chip ${u.active ? '' : 'fail'}` }, u.active ? 'Ativo' : 'Desativado')),
      h('td', { class: 'num' }, u.books),
      h('td', { class: 'muted' }, fmtWhen(u.last_login)),
      h('td', { class: 'acts' },
        h('button', { class: 'btn icon sm ghost', 'aria-label': `Editar ${u.name}`, title: 'Editar', onclick: () => editUser(u) }, ic('edit', 18)),
        h('button', { class: 'btn icon sm ghost', 'aria-label': `Excluir ${u.name}`, title: 'Excluir', onclick: () => removeUser(u) }, ic('trash', 18))))));
  };
  const editUser = async (u) => {
    const roles = [['user', 'Usuário'], ['admin', 'Administrador']];
    const done = await formDialog({
      title: u ? 'Editar usuário' : 'Novo usuário', ok: u ? 'Salvar' : 'Criar',
      fields: [
        { key: 'name', label: 'Nome', value: u?.name, required: true },
        { key: 'email', label: 'E-mail', type: 'email', value: u?.email, required: true },
        { key: 'role', label: 'Perfil', type: 'select', options: roles, value: u?.role || 'user' },
        ...(u ? [{ key: 'active', label: 'Conta ativa', type: 'checkbox', value: u.active }] : []),
        { key: 'password', label: u ? 'Nova senha' : 'Senha', type: 'password', required: !u, minlength: 8, autocomplete: 'new-password', hint: u ? 'Deixe em branco para manter a atual. Trocar a senha desconecta o usuário.' : 'De 8 a 128 caracteres.' },
      ],
      onSubmit: async (v) => {
        if (u) { await patch(`/api/users/${u.id}`, { ...v, password: v.password || undefined }); } else { await post('/api/users', v); }
      },
    });
    if (done) { toast(u ? 'Usuário atualizado.' : 'Usuário criado.'); load().catch((e) => toast(e.message, 'err')); }
  };
  const removeUser = async (u) => {
    if (!await confirmDialog({ title: `Excluir ${u.name}?`, body: u.books ? `Os ${u.books} livros dessa conta passam para você.` : 'A conta será removida.', ok: 'Excluir', danger: true })) return;
    try { await api(`/api/users/${u.id}`, { method: 'DELETE' }); toast('Usuário excluído.'); await load(); } catch (e) { toast(e.message, 'err'); }
  };
  $app.replaceChildren(heading('Usuários', 'Só administradores criam e gerenciam contas.', h('button', { class: 'btn primary', onclick: () => editUser(null) }, ic('plus', 18), 'Novo usuário')),
    h('div', { class: 'card tablewrap' }, h('table', { class: 'utable' },
      h('thead', {}, h('tr', {}, ['Pessoa', 'Perfil', 'Situação', 'Livros', 'Último acesso', ''].map((t) => h('th', { scope: 'col' }, t)))), body)));
  await load();
}

// ---------- rota ----------
async function route() {
  if (cleanup) { cleanup(); cleanup = null; }
  const [, view, arg] = location.hash.split('/');
  if (!session.user) {
    try { session.user = await api('/api/auth/me'); } catch { session.user = null; }
    renderUserbar();
    if (!session.user) { viewLogin(); return; }
  }
  try {
    if (view === 'users') await viewUsers();
    else if (view === 'new') await viewNew();
    else if (view === 'book' && arg) await viewBook(arg);
    else if (view === 'convert' && arg) await viewConvert(arg);
    else await viewLibrary();
  } catch (e) {
    if (e.status === 401) { session.user = null; renderUserbar(); viewLogin(); return; }
    $app.replaceChildren(h('div', { class: 'notice err', role: 'alert' }, ic('alert', 18), `Erro: ${e.message}`), h('a', { class: 'btn', href: '#/' }, 'Voltar à biblioteca'));
  }
  window.scrollTo({ top: 0 });
}
window.addEventListener('hashchange', route);
route();
