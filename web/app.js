import { Chess, sqName, nameToSq } from './chess-engine.js';

const GLYPHS = { k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟' };
const FILES = 'abcdefgh';

const BOARDS = [
  { name: 'Walnut', light: '#e8cfa3', dark: '#9c6f3f' },
  { name: 'Slate',  light: '#cfd8e4', dark: '#5e7187' },
  { name: 'Marble', light: '#e9e8e3', dark: '#83817b' },
  { name: 'Emerald',light: '#ebecd0', dark: '#6f8f53' },
];

const THEMES = {
  A: {
    dark: {
      bg: '#0e0c0a', surface: '#171410', surface2: '#1f1b15', border: '#2c2620',
      text: '#f1ebe0', textDim: '#9b9082', accent: '#caa257', accent2: '#e6c87e',
      accentContrast: '#1a1409', accentGlow: 'rgba(202,162,87,.55)',
      boardShadow: 'rgba(0,0,0,.7)', boardFrame: 'rgba(255,255,255,.06)',
      insetHi: 'rgba(255,255,255,.03)', danger: '#e08a6b',
    },
    light: {
      bg: '#f4efe6', surface: '#fffdf8', surface2: '#f6f0e4', border: '#e4dccc',
      text: '#231e16', textDim: '#776c5b', accent: '#9c7826', accent2: '#caa257',
      accentContrast: '#fff', accentGlow: 'rgba(156,120,38,.4)',
      boardShadow: 'rgba(120,90,40,.4)', boardFrame: 'rgba(255,255,255,.4)',
      insetHi: 'rgba(255,255,255,.7)', danger: '#c4502d',
    },
    fonts: { display: "'Marcellus', serif", body: "'Hanken Grotesk', sans-serif", mono: "'JetBrains Mono', monospace" },
    radius: '16px', radiusSm: '10px', label: 'Obsidian Edition',
  },
  B: {
    dark: {
      bg: '#080b14', surface: '#0f1626', surface2: '#16203a', border: '#243152',
      text: '#e9eefb', textDim: '#8492b0', accent: '#34dcc8', accent2: '#5b8cff',
      accentContrast: '#04130f', accentGlow: 'rgba(52,220,200,.5)',
      boardShadow: 'rgba(0,0,0,.75)', boardFrame: 'rgba(255,255,255,.05)',
      insetHi: 'rgba(255,255,255,.03)', danger: '#ff7a8a',
    },
    light: {
      bg: '#eef2fa', surface: '#ffffff', surface2: '#eef3fb', border: '#dde5f3',
      text: '#0e182f', textDim: '#5c6a86', accent: '#0bab9b', accent2: '#2f6bff',
      accentContrast: '#fff', accentGlow: 'rgba(11,171,155,.4)',
      boardShadow: 'rgba(40,60,110,.35)', boardFrame: 'rgba(255,255,255,.5)',
      insetHi: 'rgba(255,255,255,.8)', danger: '#d83a52',
    },
    fonts: { display: "'Space Grotesk', sans-serif", body: "'Space Grotesk', sans-serif", mono: "'JetBrains Mono', monospace" },
    radius: '14px', radiusSm: '9px', label: 'Midnight Edition',
  },
};

class GambitApp {
  constructor() {
    this.engine = new Chess();
    this.whiteName = 'You';
    this.blackName = 'Opponent';
    this.state = {
      direction: 'A', mode: 'dark', boardTheme: 0,
      flipped: false, selected: null, legalTargets: [],
      pending: null, showExport: false,
      fenInput: '', fenError: '', copied: false, exported: false,
      lobbyOpen: false, gameCode: null, joinCode: '',
    };
    this._cpTimer = null;
    this._exTimer = null;
    this.cacheDom();
    this.buildSwatches();
    this.bindEvents();
    this.render();
  }

  cacheDom() {
    this.$ = (id) => document.getElementById(id);
    this.dom = {
      app: this.$('app'),
      dirLabel: this.$('direction-label'),
      dirA: this.$('btn-dir-a'),
      dirB: this.$('btn-dir-b'),
      swatchGroup: this.$('swatch-group'),
      modeBtn: this.$('btn-mode'),
      lobbyBtn: this.$('btn-lobby'),
      playerTop: this.$('player-top'),
      playerBot: this.$('player-bot'),
      board: this.$('board'),
      boardWrap: this.$('board-wrap'),
      promoOverlay: this.$('promo-overlay'),
      gameoverOverlay: this.$('gameover-overlay'),
      turnDot: this.$('turn-dot'),
      statusKicker: this.$('status-kicker'),
      statusMain: this.$('status-main'),
      moveCount: this.$('move-count'),
      openingName: this.$('opening-name'),
      movesBody: this.$('moves-body'),
      movesEmpty: this.$('moves-empty'),
      undoBtn: this.$('btn-undo'),
      flipBtn: this.$('btn-flip'),
      newBtn: this.$('btn-new'),
      exportToggle: this.$('export-toggle'),
      exportChev: this.$('export-chev'),
      exportBody: this.$('export-body'),
      lobby: this.$('lobby'),
    };
  }

  buildSwatches() {
    this.dom.swatchGroup.innerHTML = BOARDS.map((b, i) =>
      `<button class="swatch-btn${i === 0 ? ' active' : ''}" data-board="${i}" title="${b.name}" style="background:linear-gradient(135deg,${b.light} 0 50%,${b.dark} 50% 100%)"></button>`
    ).join('');
  }

  bindEvents() {
    this.dom.dirA.addEventListener('click', () => this.setDirection('A'));
    this.dom.dirB.addEventListener('click', () => this.setDirection('B'));
    this.dom.swatchGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-board]');
      if (btn) this.setBoardTheme(+btn.dataset.board);
    });
    this.dom.modeBtn.addEventListener('click', () => this.toggleMode());
    this.dom.lobbyBtn.addEventListener('click', () => this.openLobby());
    this.dom.board.addEventListener('click', (e) => {
      const btn = e.target.closest('[data-sq]');
      if (btn) this.onSquareClick(+btn.dataset.sq);
    });
    this.dom.undoBtn.addEventListener('click', () => this.undo());
    this.dom.flipBtn.addEventListener('click', () => this.flip());
    this.dom.newBtn.addEventListener('click', () => this.newGame());
    this.dom.exportToggle.addEventListener('click', () => this.toggleExport());
  }

  // --- State helpers ---
  setDirection(d) { this.state.direction = d; this.render(); }
  setBoardTheme(i) { this.state.boardTheme = i; this.render(); }
  toggleMode() { this.state.mode = this.state.mode === 'dark' ? 'light' : 'dark'; this.render(); }

  // --- Theme ---
  getTheme() {
    const dir = THEMES[this.state.direction];
    const c = dir[this.state.mode];
    const board = BOARDS[this.state.boardTheme] || BOARDS[0];
    return { c, dir, board };
  }

  applyTheme() {
    const { c, dir, board } = this.getTheme();
    const el = this.dom.app;
    const v = (n, val) => el.style.setProperty(n, val);
    v('--bg', c.bg); v('--surface', c.surface); v('--surface-2', c.surface2); v('--border', c.border);
    v('--text', c.text); v('--text-dim', c.textDim); v('--accent', c.accent); v('--accent-2', c.accent2);
    v('--accent-contrast', c.accentContrast); v('--accent-glow', c.accentGlow); v('--danger', c.danger);
    v('--board-light', board.light); v('--board-dark', board.dark);
    v('--board-shadow', c.boardShadow); v('--board-frame', c.boardFrame); v('--inset-hi', c.insetHi);
    v('--piece-white', '#f7f3ea'); v('--piece-black', '#1a160f');
    v('--legal', `color-mix(in srgb, ${c.accent} 78%, transparent)`);
    v('--last', `color-mix(in srgb, ${c.accent2} 42%, transparent)`);
    v('--sel', c.accent); v('--check', '#e0533c');
    v('--font-display', dir.fonts.display); v('--font-body', dir.fonts.body); v('--font-mono', dir.fonts.mono);
    v('--radius', dir.radius); v('--radius-sm', dir.radiusSm);
  }

  // --- Render orchestrator ---
  render() {
    this.applyTheme();
    this.renderTopBar();
    this.renderPlayers();
    this.renderBoard();
    this.renderStatus();
    this.renderMoveList();
    this.renderControls();
    this.renderExportPanel();
    this.renderPromo();
    this.renderGameOver();
    if (this.state.lobbyOpen) this.renderLobby();
  }

  renderTopBar() {
    const d = this.state.direction;
    this.dom.dirLabel.textContent = THEMES[d].label;
    this.dom.dirA.classList.toggle('active', d === 'A');
    this.dom.dirB.classList.toggle('active', d === 'B');
    this.dom.modeBtn.textContent = this.state.mode === 'dark' ? '☀' : '☾';
    this.dom.swatchGroup.querySelectorAll('.swatch-btn').forEach((btn, i) => {
      btn.classList.toggle('active', i === this.state.boardTheme);
    });
  }

  // --- Players ---
  renderPlayerStrip(el, color, name) {
    const eng = this.engine;
    const isWhite = color === 'w';
    const turn = eng.turn;
    const inCheck = eng.inCheck(turn);
    const active = turn === color;
    const subtitle = (isWhite ? 'White' : 'Black') + (active && inCheck ? ' · in check' : '');
    const cap = eng.captured();
    const pieces = isWhite ? cap.black : cap.white;
    const mat = eng.material();
    const adv = isWhite ? (mat > 0 ? '+' + mat : '') : (mat < 0 ? '+' + (-mat) : '');

    el.className = 'player-strip' + (active ? ' active' : '');
    el.innerHTML = `
      <div class="player-info">
        <div class="player-avatar ${isWhite ? 'white-av' : 'black-av'}">${(name || (isWhite ? 'W' : 'B'))[0].toUpperCase()}</div>
        <div>
          <div class="player-name">${this.esc(name)}</div>
          <div class="player-sub">${subtitle}</div>
        </div>
      </div>
      <div style="display:flex;align-items:center;gap:10px">
        <div class="captured-group">${pieces.map(p =>
          `<span class="captured-piece" style="color:${p === p.toUpperCase() ? 'var(--piece-white)' : 'var(--piece-black)'}">${GLYPHS[p.toLowerCase()]}</span>`
        ).join('')}</div>
        <span class="material-adv" style="opacity:${adv ? 1 : 0}">${adv}</span>
      </div>`;
  }

  renderPlayers() {
    const flip = this.state.flipped;
    this.renderPlayerStrip(this.dom.playerTop, flip ? 'w' : 'b', flip ? this.whiteName : this.blackName);
    this.renderPlayerStrip(this.dom.playerBot, flip ? 'b' : 'w', flip ? this.blackName : this.whiteName);
  }

  // --- Board ---
  lastMove() {
    const h = this.engine.history;
    if (!h.length) return null;
    const uci = h[h.length - 1].uci;
    const from = nameToSq(uci.slice(0, 2));
    const to = nameToSq(uci.slice(2, 4));
    return [from, to];
  }

  renderBoard() {
    const eng = this.engine;
    const { flipped, selected, legalTargets } = this.state;
    const last = this.lastMove();
    const checkSq = eng.inCheck(eng.turn) ? eng.kingSquare(eng.turn) : -1;
    const ranks = flipped ? [0,1,2,3,4,5,6,7] : [7,6,5,4,3,2,1,0];
    const files = flipped ? [7,6,5,4,3,2,1,0] : [0,1,2,3,4,5,6,7];

    let html = '';
    for (const r of ranks) {
      for (const f of files) {
        const idx = f + r * 8;
        const isLight = (f + r) % 2 === 1;
        const piece = eng.board[idx];
        const isSel = selected === idx;
        const isLast = last && (last[0] === idx || last[1] === idx);
        const isTarget = legalTargets.includes(idx);
        const isCheck = idx === checkSq;

        let bg = isLight ? 'var(--board-light)' : 'var(--board-dark)';
        if (isLast) bg = `linear-gradient(0deg,var(--last),var(--last)),${bg}`;

        let shadow = '';
        let anim = '';
        if (isSel) shadow = 'box-shadow:inset 0 0 0 4px var(--sel);';
        if (isCheck) { shadow = 'box-shadow:inset 0 0 0 3px var(--check),inset 0 0 26px -4px var(--check);'; anim = 'animation:gb-pulse 1.6s infinite;'; }

        const cursor = (piece || isTarget) ? 'pointer' : 'default';
        let inner = '';

        if (piece) {
          const pw = piece === piece.toUpperCase();
          inner += `<span class="sq-piece ${pw ? 'white' : 'black'}">${GLYPHS[piece.toLowerCase()]}</span>`;
        }
        if (isTarget && !piece) inner += '<span class="legal-dot"></span>';
        if (isTarget && piece) inner += '<span class="legal-ring"></span>';

        const isBottomRow = flipped ? r === 7 : r === 0;
        const isLeftCol = flipped ? f === 7 : f === 0;
        const lblColor = isLight ? 'var(--board-dark)' : 'var(--board-light)';
        if (isBottomRow) inner += `<span class="sq-label file" style="color:${lblColor}">${FILES[f]}</span>`;
        if (isLeftCol) inner += `<span class="sq-label rank" style="color:${lblColor}">${r + 1}</span>`;

        html += `<button data-sq="${idx}" style="background:${bg};cursor:${cursor};${shadow}${anim}">${inner}</button>`;
      }
    }
    this.dom.board.innerHTML = html;
  }

  onSquareClick(idx) {
    const eng = this.engine;
    if (this.state.pending || eng.isGameOver()) return;
    const sel = this.state.selected;

    if (sel !== null && this.state.legalTargets.includes(idx)) {
      const p = eng.board[sel];
      const promoRank = eng.turn === 'w' ? 7 : 0;
      if (p && p.toLowerCase() === 'p' && Math.floor(idx / 8) === promoRank) {
        this.state.pending = { from: sel, to: idx };
        this.state.selected = null;
        this.state.legalTargets = [];
        this.render();
        return;
      }
      eng.move(sel, idx);
      this.state.selected = null;
      this.state.legalTargets = [];
      this.render();
      return;
    }

    const piece = eng.board[idx];
    const isOwn = piece && ((piece === piece.toUpperCase() ? 'w' : 'b') === eng.turn);
    if (isOwn) {
      const tg = eng.legalMoves(idx).map(m => m.to);
      this.state.selected = idx;
      this.state.legalTargets = [...new Set(tg)];
    } else {
      this.state.selected = null;
      this.state.legalTargets = [];
    }
    this.render();
  }

  // --- Promotion ---
  renderPromo() {
    const el = this.dom.promoOverlay;
    if (!this.state.pending) { el.classList.add('hidden'); return; }
    el.classList.remove('hidden');
    const turn = this.engine.turn;
    el.className = 'overlay promo-overlay';
    el.innerHTML = `
      <div class="promo-card">
        <div class="promo-kicker">Promote to</div>
        <div class="promo-choices">
          ${['q','r','b','n'].map(pr => `<button class="promo-btn" data-promo="${pr}">${GLYPHS[pr]}</button>`).join('')}
        </div>
      </div>`;
    el.querySelectorAll('[data-promo]').forEach(btn => {
      btn.addEventListener('click', () => this.choosePromo(btn.dataset.promo));
    });
  }

  choosePromo(pr) {
    const { from, to } = this.state.pending;
    this.engine.move(from, to, pr);
    this.state.pending = null;
    this.render();
  }

  // --- Game Over ---
  renderGameOver() {
    const el = this.dom.gameoverOverlay;
    const result = this.engine.resultText();
    if (!result.over) { el.classList.add('hidden'); return; }
    el.classList.remove('hidden');
    el.className = 'overlay gameover-overlay';
    const icon = result.winner === 'w' ? '♔' : result.winner === 'b' ? '♚' : '½';
    el.innerHTML = `
      <div class="gameover-inner">
        <div class="gameover-icon">${icon}</div>
        <div class="gameover-title">${this.esc(result.title)}</div>
        <div class="gameover-sub">${this.esc(result.sub)}</div>
        <div class="gameover-actions">
          <button class="gameover-new" id="go-new">New game</button>
          <button class="gameover-rematch" id="go-lobby">Rematch online</button>
        </div>
      </div>`;
    this.$('go-new').addEventListener('click', () => this.newGame());
    this.$('go-lobby').addEventListener('click', () => this.openLobby());
  }

  // --- Status ---
  renderStatus() {
    const eng = this.engine;
    const turn = eng.turn;
    const inCheck = eng.inCheck(turn);
    const result = eng.resultText();

    this.dom.turnDot.style.background = turn === 'w' ? 'var(--piece-white)' : 'var(--piece-black)';
    this.dom.turnDot.style.boxShadow = '0 0 0 2px var(--border)' + (inCheck ? ', 0 0 0 4px var(--check)' : '');
    this.dom.statusKicker.textContent = result.over ? 'Game over' : (inCheck ? 'Check!' : 'To move');
    this.dom.statusMain.textContent = result.over ? result.title : (turn === 'w' ? 'White' : 'Black');
    this.dom.moveCount.textContent = Math.ceil(eng.history.length / 2);
  }

  // --- Move List ---
  getOpeningName() {
    const h = this.engine.history;
    if (!h.length) return '';
    const first = h[0].san;
    const map = { e4: "King's Pawn", d4: "Queen's Pawn", Nf3: 'Réti', c4: 'English', g3: 'Hungarian' };
    return map[first] || 'Game';
  }

  renderMoveList() {
    const h = this.engine.history;
    this.dom.openingName.textContent = this.getOpeningName();
    if (!h.length) {
      this.dom.movesEmpty.classList.remove('hidden');
      this.dom.movesBody.querySelectorAll('.move-row').forEach(r => r.remove());
      return;
    }
    this.dom.movesEmpty.classList.add('hidden');
    const total = h.length;
    let html = '';
    for (let i = 0; i < h.length; i += 2) {
      const isLastW = i === total - 1;
      const isLastB = i + 1 === total - 1;
      const zebra = (i / 2) % 2 === 1 ? ' zebra' : '';
      html += `<div class="move-row${zebra}">
        <span class="move-num">${i / 2 + 1}.</span>
        <span class="move-san${isLastW ? ' current' : ''}">${h[i] ? h[i].san : ''}</span>
        <span class="move-san${isLastB ? ' current' : ''}">${h[i + 1] ? h[i + 1].san : ''}</span>
      </div>`;
    }
    const body = this.dom.movesBody;
    const empNode = this.dom.movesEmpty;
    body.innerHTML = '';
    body.appendChild(empNode);
    body.insertAdjacentHTML('beforeend', html);
    body.scrollTop = body.scrollHeight;
  }

  // --- Controls ---
  renderControls() {
    const hasHistory = this.engine.history.length > 0;
    this.dom.undoBtn.classList.toggle('disabled', !hasHistory);
  }

  // --- Export Panel ---
  toggleExport() {
    this.state.showExport = !this.state.showExport;
    this.render();
  }

  renderExportPanel() {
    const el = this.dom.exportBody;
    const chev = this.dom.exportChev;
    if (!this.state.showExport) {
      el.classList.add('hidden');
      chev.classList.remove('open');
      return;
    }
    el.classList.remove('hidden');
    chev.classList.add('open');

    el.className = 'export-body';
    el.innerHTML = `
      <div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
          <span class="export-label" style="margin-bottom:0">Current FEN</span>
          <button class="export-copy-btn" id="btn-copy-fen">${this.state.copied ? 'Copied ✓' : 'Copy'}</button>
        </div>
        <div class="fen-display">${this.esc(this.engine.fen())}</div>
      </div>
      <div>
        <div class="export-label">Load a position</div>
        <input class="fen-input" id="fen-input" placeholder="Paste FEN…" value="${this.esc(this.state.fenInput)}" />
        <div class="export-actions">
          <button class="btn-load-fen" id="btn-load-fen">Load FEN</button>
          <button class="btn-copy-pgn" id="btn-copy-pgn">${this.state.exported ? 'Copied ✓' : 'Copy PGN'}</button>
        </div>
        ${this.state.fenError ? `<div class="fen-error">${this.esc(this.state.fenError)}</div>` : ''}
      </div>`;

    this.$('btn-copy-fen').addEventListener('click', () => this.copyFen());
    this.$('btn-load-fen').addEventListener('click', () => this.loadFen());
    this.$('btn-copy-pgn').addEventListener('click', () => this.copyPgn());
    this.$('fen-input').addEventListener('input', (e) => {
      this.state.fenInput = e.target.value;
      this.state.fenError = '';
    });
  }

  copyFen() {
    try { navigator.clipboard.writeText(this.engine.fen()); } catch {}
    this.state.copied = true;
    this.render();
    clearTimeout(this._cpTimer);
    this._cpTimer = setTimeout(() => { this.state.copied = false; this.render(); }, 1500);
  }

  copyPgn() {
    const pgn = this.engine.history.map((m, i) => (i % 2 === 0 ? (i / 2 + 1) + '. ' : '') + m.san).join(' ');
    try { navigator.clipboard.writeText(pgn); } catch {}
    this.state.exported = true;
    this.render();
    clearTimeout(this._exTimer);
    this._exTimer = setTimeout(() => { this.state.exported = false; this.render(); }, 1500);
  }

  loadFen() {
    const v = this.state.fenInput.trim();
    if (!v) return;
    try {
      const test = new Chess(v);
      if (test.board.filter(Boolean).length === 0) throw new Error('empty');
      this.engine = test;
      this.state.selected = null;
      this.state.legalTargets = [];
      this.state.pending = null;
      this.state.fenError = '';
      this.state.fenInput = '';
      this.render();
    } catch {
      this.state.fenError = "That doesn't look like a valid FEN.";
      this.render();
    }
  }

  // --- Actions ---
  undo() {
    if (!this.engine.history.length) return;
    this.engine.undo();
    this.state.selected = null;
    this.state.legalTargets = [];
    this.state.pending = null;
    this.render();
  }

  flip() {
    this.state.flipped = !this.state.flipped;
    this.render();
  }

  newGame() {
    this.engine.reset();
    this.state.selected = null;
    this.state.legalTargets = [];
    this.state.pending = null;
    this.state.fenError = '';
    this.render();
  }

  // --- Lobby ---
  openLobby() {
    this.state.lobbyOpen = true;
    this.renderLobby();
  }

  closeLobby() {
    this.state.lobbyOpen = false;
    this.dom.lobby.classList.add('hidden');
    this.dom.lobby.innerHTML = '';
  }

  renderLobby() {
    const el = this.dom.lobby;
    el.classList.remove('hidden');
    const hasCode = !!this.state.gameCode;
    const joinLen = this.state.joinCode.length;
    const joinReady = joinLen >= 4;

    el.innerHTML = `
      <div class="lobby-backdrop">
        <div class="lobby-card">
          <button class="lobby-close" id="lobby-close">✕</button>
          <div class="lobby-kicker">Play a friend</div>
          <div class="lobby-title">Multiplayer</div>
          <div class="lobby-grid">
            <div class="lobby-panel">
              <div class="lobby-panel-icon">♔</div>
              <div class="lobby-panel-title">Create game</div>
              <div class="lobby-panel-desc">Generate a code and share it. You play White.</div>
              ${hasCode ? `
                <div class="lobby-code-box">
                  <div class="lobby-code-label">Room code</div>
                  <div class="lobby-code-val">${this.state.gameCode}</div>
                </div>
                <button class="lobby-btn" id="lobby-enter">Enter board →</button>
              ` : `
                <button class="lobby-btn generate" id="lobby-gen">Generate code</button>
              `}
            </div>
            <div class="lobby-panel">
              <div class="lobby-panel-icon">♚</div>
              <div class="lobby-panel-title">Join game</div>
              <div class="lobby-panel-desc">Enter a friend's code. You play Black.</div>
              <input class="join-input" id="join-input" placeholder="ABC123" maxlength="6" value="${this.esc(this.state.joinCode)}" />
              <button class="lobby-btn${joinReady ? '' : ' disabled'}" id="lobby-join">Join board →</button>
            </div>
          </div>
          <div class="lobby-hint">Real-time play is wired up in the Streamlit backend — this is the matchmaking UI.</div>
        </div>
      </div>`;

    this.$('lobby-close').addEventListener('click', () => this.closeLobby());
    const genBtn = this.$('lobby-gen');
    if (genBtn) genBtn.addEventListener('click', () => this.createGame());
    const enterBtn = this.$('lobby-enter');
    if (enterBtn) enterBtn.addEventListener('click', () => this.startCreated());
    this.$('join-input').addEventListener('input', (e) => {
      this.state.joinCode = e.target.value.toUpperCase().slice(0, 6);
      this.renderLobby();
    });
    this.$('lobby-join').addEventListener('click', () => this.joinGame());
  }

  createGame() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    this.state.gameCode = Array.from({ length: 6 }, () => chars[Math.floor(Math.random() * chars.length)]).join('');
    this.renderLobby();
  }

  startCreated() {
    this.engine.reset();
    this.whiteName = 'You';
    this.blackName = 'Guest';
    this.state.lobbyOpen = false;
    this.state.flipped = false;
    this.state.selected = null;
    this.state.legalTargets = [];
    this.state.pending = null;
    this.closeLobby();
    this.render();
  }

  joinGame() {
    if (this.state.joinCode.length < 4) return;
    this.engine.reset();
    this.whiteName = 'Host';
    this.blackName = 'You';
    this.state.flipped = true;
    this.state.selected = null;
    this.state.legalTargets = [];
    this.state.pending = null;
    this.closeLobby();
    this.render();
  }

  esc(s) {
    const d = document.createElement('div');
    d.textContent = s || '';
    return d.innerHTML;
  }
}

document.addEventListener('DOMContentLoaded', () => { window.app = new GambitApp(); });
