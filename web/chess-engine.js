// Compact but complete chess engine.
// Squares 0..63, square = file + rank*8, a1=0, h1=7, a8=56 (mirrors python-chess).
// White pieces uppercase PNBRQK, black lowercase.

const WHITE = "w", BLACK = "b";
const START = [
  "R","N","B","Q","K","B","N","R",
  "P","P","P","P","P","P","P","P",
  null,null,null,null,null,null,null,null,
  null,null,null,null,null,null,null,null,
  null,null,null,null,null,null,null,null,
  null,null,null,null,null,null,null,null,
  "p","p","p","p","p","p","p","p",
  "r","n","b","q","k","b","n","r",
];

const file = (sq) => sq % 8;
const rank = (sq) => Math.floor(sq / 8);
const onBoard = (f, r) => f >= 0 && f < 8 && r >= 0 && r < 8;
const colorOf = (p) => (p === p.toUpperCase() ? WHITE : BLACK);
const isUpper = (p) => p === p.toUpperCase();

const KNIGHT_D = [[1,2],[2,1],[2,-1],[1,-2],[-1,-2],[-2,-1],[-2,1],[-1,2]];
const KING_D = [[1,0],[1,1],[0,1],[-1,1],[-1,0],[-1,-1],[0,-1],[1,-1]];
const BISHOP_D = [[1,1],[1,-1],[-1,1],[-1,-1]];
const ROOK_D = [[1,0],[-1,0],[0,1],[0,-1]];

export class Chess {
  constructor(fen) {
    if (fen) this.loadFen(fen);
    else this.reset();
  }

  reset() {
    this.board = START.slice();
    this.turn = WHITE;
    this.castling = { K: true, Q: true, k: true, q: true };
    this.ep = null;
    this.history = [];
    this._stack = [];
  }

  clone() {
    const c = new Chess();
    c.board = this.board.slice();
    c.turn = this.turn;
    c.castling = { ...this.castling };
    c.ep = this.ep;
    return c;
  }

  _snapshot() {
    return {
      board: this.board.slice(),
      turn: this.turn,
      castling: { ...this.castling },
      ep: this.ep,
    };
  }
  _restore(s) {
    this.board = s.board.slice();
    this.turn = s.turn;
    this.castling = { ...s.castling };
    this.ep = s.ep;
  }

  kingSquare(color) {
    const k = color === WHITE ? "K" : "k";
    return this.board.indexOf(k);
  }

  isAttacked(sq, byColor) {
    const f = file(sq), r = rank(sq);
    const pdir = byColor === WHITE ? 1 : -1;
    for (const df of [-1, 1]) {
      const nf = f + df, nr = r - pdir;
      if (onBoard(nf, nr)) {
        const p = this.board[nf + nr * 8];
        if (p && colorOf(p) === byColor && p.toLowerCase() === "p") return true;
      }
    }
    for (const [df, dr] of KNIGHT_D) {
      const nf = f + df, nr = r + dr;
      if (onBoard(nf, nr)) {
        const p = this.board[nf + nr * 8];
        if (p && colorOf(p) === byColor && p.toLowerCase() === "n") return true;
      }
    }
    for (const [df, dr] of KING_D) {
      const nf = f + df, nr = r + dr;
      if (onBoard(nf, nr)) {
        const p = this.board[nf + nr * 8];
        if (p && colorOf(p) === byColor && p.toLowerCase() === "k") return true;
      }
    }
    const checkSlide = (dirs, types) => {
      for (const [df, dr] of dirs) {
        let nf = f + df, nr = r + dr;
        while (onBoard(nf, nr)) {
          const p = this.board[nf + nr * 8];
          if (p) {
            if (colorOf(p) === byColor && types.includes(p.toLowerCase())) return true;
            break;
          }
          nf += df; nr += dr;
        }
      }
      return false;
    };
    if (checkSlide(BISHOP_D, ["b", "q"])) return true;
    if (checkSlide(ROOK_D, ["r", "q"])) return true;
    return false;
  }

  inCheck(color) {
    return this.isAttacked(this.kingSquare(color), color === WHITE ? BLACK : WHITE);
  }

  _pseudo(sq) {
    const p = this.board[sq];
    if (!p) return [];
    const color = colorOf(p);
    const f = file(sq), r = rank(sq);
    const out = [];
    const add = (to, extra = {}) => out.push({ from: sq, to, ...extra });
    const type = p.toLowerCase();
    const enemy = (t) => t && colorOf(t) !== color;
    const empty = (t) => !t;

    if (type === "p") {
      const dir = color === WHITE ? 1 : -1;
      const startRank = color === WHITE ? 1 : 6;
      const promoRank = color === WHITE ? 7 : 0;
      const one = f + (r + dir) * 8;
      if (onBoard(f, r + dir) && empty(this.board[one])) {
        if (r + dir === promoRank) for (const pr of ["q","r","b","n"]) add(one, { promotion: pr });
        else add(one);
        const two = f + (r + 2 * dir) * 8;
        if (r === startRank && empty(this.board[two])) add(two, { flag: "double" });
      }
      for (const df of [-1, 1]) {
        const nf = f + df, nr = r + dir;
        if (!onBoard(nf, nr)) continue;
        const tsq = nf + nr * 8;
        const t = this.board[tsq];
        if (enemy(t)) {
          if (nr === promoRank) for (const pr of ["q","r","b","n"]) add(tsq, { promotion: pr });
          else add(tsq);
        } else if (tsq === this.ep) {
          add(tsq, { flag: "ep" });
        }
      }
    } else if (type === "n") {
      for (const [df, dr] of KNIGHT_D) {
        const nf = f + df, nr = r + dr;
        if (!onBoard(nf, nr)) continue;
        const t = this.board[nf + nr * 8];
        if (empty(t) || enemy(t)) add(nf + nr * 8);
      }
    } else if (type === "k") {
      for (const [df, dr] of KING_D) {
        const nf = f + df, nr = r + dr;
        if (!onBoard(nf, nr)) continue;
        const t = this.board[nf + nr * 8];
        if (empty(t) || enemy(t)) add(nf + nr * 8);
      }
      const opp = color === WHITE ? BLACK : WHITE;
      const homeRank = color === WHITE ? 0 : 7;
      if (r === homeRank && f === 4 && !this.isAttacked(sq, opp)) {
        const kSide = color === WHITE ? this.castling.K : this.castling.k;
        const qSide = color === WHITE ? this.castling.Q : this.castling.q;
        const idx = (ff) => ff + homeRank * 8;
        if (kSide && empty(this.board[idx(5)]) && empty(this.board[idx(6)]) &&
            !this.isAttacked(idx(5), opp) && !this.isAttacked(idx(6), opp)) {
          add(idx(6), { flag: "castleK" });
        }
        if (qSide && empty(this.board[idx(3)]) && empty(this.board[idx(2)]) && empty(this.board[idx(1)]) &&
            !this.isAttacked(idx(3), opp) && !this.isAttacked(idx(2), opp)) {
          add(idx(2), { flag: "castleQ" });
        }
      }
    } else {
      const dirs = type === "b" ? BISHOP_D : type === "r" ? ROOK_D : KING_D;
      for (const [df, dr] of dirs) {
        let nf = f + df, nr = r + dr;
        while (onBoard(nf, nr)) {
          const t = this.board[nf + nr * 8];
          if (empty(t)) add(nf + nr * 8);
          else { if (enemy(t)) add(nf + nr * 8); break; }
          nf += df; nr += dr;
        }
      }
    }
    return out;
  }

  legalMoves(fromSq = null) {
    const moves = [];
    const squares = fromSq === null ? [...Array(64).keys()] : [fromSq];
    for (const sq of squares) {
      const p = this.board[sq];
      if (!p || colorOf(p) !== this.turn) continue;
      for (const m of this._pseudo(sq)) {
        const snap = this._snapshot();
        this._apply(m);
        const legal = !this.inCheck(snap.turn);
        this._restore(snap);
        if (legal) moves.push(m);
      }
    }
    return moves;
  }

  legalBySquare() {
    const map = {};
    for (const m of this.legalMoves()) {
      (map[m.from] = map[m.from] || new Set()).add(m.to);
    }
    const out = {};
    for (const k in map) out[k] = [...map[k]];
    return out;
  }

  _apply(m) {
    const p = this.board[m.from];
    const color = colorOf(p);
    const captured = this.board[m.to];
    this.board[m.to] = m.promotion ? (color === WHITE ? m.promotion.toUpperCase() : m.promotion) : p;
    this.board[m.from] = null;
    this.ep = null;

    if (m.flag === "double") {
      this.ep = m.to + (color === WHITE ? -8 : 8);
    } else if (m.flag === "ep") {
      const capSq = m.to + (color === WHITE ? -8 : 8);
      this.board[capSq] = null;
    } else if (m.flag === "castleK") {
      const hr = rank(m.from);
      this.board[5 + hr * 8] = this.board[7 + hr * 8];
      this.board[7 + hr * 8] = null;
    } else if (m.flag === "castleQ") {
      const hr = rank(m.from);
      this.board[3 + hr * 8] = this.board[0 + hr * 8];
      this.board[0 + hr * 8] = null;
    }

    if (p === "K") { this.castling.K = false; this.castling.Q = false; }
    if (p === "k") { this.castling.k = false; this.castling.q = false; }
    if (m.from === 0 || m.to === 0) this.castling.Q = false;
    if (m.from === 7 || m.to === 7) this.castling.K = false;
    if (m.from === 56 || m.to === 56) this.castling.q = false;
    if (m.from === 63 || m.to === 63) this.castling.k = false;

    this.turn = color === WHITE ? BLACK : WHITE;
    return captured;
  }

  findMove(from, to, promotion = null) {
    for (const m of this.legalMoves(from)) {
      if (m.to === to && (!m.promotion || m.promotion === (promotion || "q"))) {
        if (m.promotion && promotion && m.promotion !== promotion) continue;
        return m;
      }
    }
    return null;
  }

  move(from, to, promotion = null) {
    const m = this.findMove(from, to, promotion);
    if (!m) return null;
    const san = this._san(m);
    this._stack.push(this._snapshot());
    const color = this.turn;
    const captured = this._apply(m);
    this.history.push({
      uci: this._uci(m), san, color,
      capture: !!captured || m.flag === "ep",
      capturedPiece: m.flag === "ep" ? (color === WHITE ? "p" : "P") : captured || null,
    });
    return san;
  }

  undo() {
    if (!this._stack.length) return;
    this._restore(this._stack.pop());
    this.history.pop();
  }

  _uci(m) {
    return sqName(m.from) + sqName(m.to) + (m.promotion || "");
  }

  _san(m) {
    const p = this.board[m.from];
    const type = p.toLowerCase();
    if (m.flag === "castleK") return this._suffix(m, "O-O");
    if (m.flag === "castleQ") return this._suffix(m, "O-O-O");
    const dest = sqName(m.to);
    const capture = !!this.board[m.to] || m.flag === "ep";
    let s = "";
    if (type === "p") {
      if (capture) s += "abcdefgh"[file(m.from)] + "x";
      s += dest;
      if (m.promotion) s += "=" + m.promotion.toUpperCase();
    } else {
      s += p.toUpperCase();
      s += this._disambig(m);
      if (capture) s += "x";
      s += dest;
    }
    return this._suffix(m, s);
  }

  _disambig(m) {
    const p = this.board[m.from];
    const others = [];
    for (let sq = 0; sq < 64; sq++) {
      if (sq === m.from) continue;
      const q = this.board[sq];
      if (q && q === p && colorOf(q) === colorOf(p)) {
        if (this.legalMoves(sq).some((x) => x.to === m.to)) others.push(sq);
      }
    }
    if (!others.length) return "";
    const sameFile = others.some((sq) => file(sq) === file(m.from));
    const sameRank = others.some((sq) => rank(sq) === rank(m.from));
    if (!sameFile) return "abcdefgh"[file(m.from)];
    if (!sameRank) return String(rank(m.from) + 1);
    return "abcdefgh"[file(m.from)] + String(rank(m.from) + 1);
  }

  _suffix(m, s) {
    const snap = this._snapshot();
    this._apply(m);
    const opp = this.turn;
    let suf = "";
    if (this.inCheck(opp)) suf = this.legalMoves().length === 0 ? "#" : "+";
    this._restore(snap);
    return s + suf;
  }

  isCheckmate() { return this.inCheck(this.turn) && this.legalMoves().length === 0; }
  isStalemate() { return !this.inCheck(this.turn) && this.legalMoves().length === 0; }
  isGameOver() { return this.legalMoves().length === 0 || this.isInsufficient(); }

  isInsufficient() {
    const pieces = this.board.filter(Boolean).map((p) => p.toLowerCase());
    const nonKing = pieces.filter((p) => p !== "k");
    if (nonKing.length === 0) return true;
    if (nonKing.length === 1 && (nonKing[0] === "b" || nonKing[0] === "n")) return true;
    return false;
  }

  resultText() {
    if (this.isCheckmate()) return { over: true, title: "Checkmate", sub: (this.turn === WHITE ? "Black" : "White") + " wins", winner: this.turn === WHITE ? BLACK : WHITE };
    if (this.isStalemate()) return { over: true, title: "Stalemate", sub: "Draw", winner: null };
    if (this.isInsufficient()) return { over: true, title: "Draw", sub: "Insufficient material", winner: null };
    return { over: false };
  }

  fen() {
    let rows = [];
    for (let r = 7; r >= 0; r--) {
      let row = "", empty = 0;
      for (let f = 0; f < 8; f++) {
        const p = this.board[f + r * 8];
        if (!p) empty++;
        else { if (empty) { row += empty; empty = 0; } row += p; }
      }
      if (empty) row += empty;
      rows.push(row);
    }
    const cr = (this.castling.K ? "K" : "") + (this.castling.Q ? "Q" : "") +
               (this.castling.k ? "k" : "") + (this.castling.q ? "q" : "") || "-";
    return rows.join("/") + " " + this.turn + " " + cr + " " + (this.ep !== null ? sqName(this.ep) : "-") + " 0 1";
  }

  loadFen(fen) {
    const parts = fen.trim().split(/\s+/);
    const board = new Array(64).fill(null);
    const rows = parts[0].split("/");
    for (let r = 0; r < 8; r++) {
      let f = 0;
      for (const ch of rows[r]) {
        if (/\d/.test(ch)) f += parseInt(ch);
        else { board[f + (7 - r) * 8] = ch; f++; }
      }
    }
    this.board = board;
    this.turn = parts[1] === "b" ? BLACK : WHITE;
    const cr = parts[2] || "";
    this.castling = { K: cr.includes("K"), Q: cr.includes("Q"), k: cr.includes("k"), q: cr.includes("q") };
    this.ep = parts[3] && parts[3] !== "-" ? nameToSq(parts[3]) : null;
    this.history = [];
    this._stack = [];
  }

  material() {
    const val = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };
    let bal = 0;
    for (const p of this.board) {
      if (!p) continue;
      const v = val[p.toLowerCase()];
      bal += isUpper(p) ? v : -v;
    }
    return bal;
  }

  captured() {
    const counts = { P:8,N:2,B:2,R:2,Q:1,K:1,p:8,n:2,b:2,r:2,q:1,k:1 };
    const cur = {};
    for (const p of this.board) if (p) cur[p] = (cur[p] || 0) + 1;
    const order = ["Q","R","B","N","P"];
    const white = [], black = [];
    for (const t of order) {
      for (let i = 0; i < counts[t] - (cur[t] || 0); i++) white.push(t);
      const lt = t.toLowerCase();
      for (let i = 0; i < counts[lt] - (cur[lt] || 0); i++) black.push(lt);
    }
    return { white, black };
  }
}

export function sqName(sq) {
  return "abcdefgh"[file(sq)] + String(rank(sq) + 1);
}
export function nameToSq(name) {
  return "abcdefgh".indexOf(name[0]) + (parseInt(name[1]) - 1) * 8;
}
