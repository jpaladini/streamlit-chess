"""
Custom pure-Python chess engine.

Drop-in replacement for the subset of python-chess used by the Streamlit app.
Implements board representation, legal move generation (including castling,
en passant, promotion), check / checkmate / stalemate detection, FEN
parsing & serialisation, SAN notation, and draw conditions.
"""

# ---------------------------------------------------------------------------
# Piece types
# ---------------------------------------------------------------------------
PAWN = 1
KNIGHT = 2
BISHOP = 3
ROOK = 4
QUEEN = 5
KING = 6

# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
WHITE = True
BLACK = False

# ---------------------------------------------------------------------------
# Squares  (0 = a1, 1 = b1, …, 63 = h8  – same layout as python-chess)
# ---------------------------------------------------------------------------
SQUARES = list(range(64))

_FILE_NAMES = "abcdefgh"
_SQUARE_NAMES = [f + str(r) for r in range(1, 9) for f in _FILE_NAMES]


def _square_file(sq: int) -> int:
    return sq & 7


def _square_rank(sq: int) -> int:
    return sq >> 3


def _square_name(sq: int) -> str:
    return _SQUARE_NAMES[sq]


def _parse_square(name: str) -> int:
    return (int(name[1]) - 1) * 8 + (ord(name[0]) - ord("a"))


# ---------------------------------------------------------------------------
# Piece
# ---------------------------------------------------------------------------
_PIECE_SYMBOLS = {PAWN: "p", KNIGHT: "n", BISHOP: "b", ROOK: "r", QUEEN: "q", KING: "k"}


class Piece:
    __slots__ = ("piece_type", "color")

    def __init__(self, piece_type: int, color: bool):
        self.piece_type = piece_type
        self.color = color

    def symbol(self) -> str:
        s = _PIECE_SYMBOLS[self.piece_type]
        return s.upper() if self.color == WHITE else s

    def __eq__(self, other):
        if not isinstance(other, Piece):
            return NotImplemented
        return self.piece_type == other.piece_type and self.color == other.color

    def __hash__(self):
        return hash((self.piece_type, self.color))

    def __repr__(self):
        return f"Piece.from_symbol('{self.symbol()}')"


# ---------------------------------------------------------------------------
# Move
# ---------------------------------------------------------------------------
_PROMO_CHARS = {QUEEN: "q", ROOK: "r", BISHOP: "b", KNIGHT: "n"}
_PROMO_FROM_CHAR = {v: k for k, v in _PROMO_CHARS.items()}


class Move:
    __slots__ = ("from_square", "to_square", "promotion")

    def __init__(self, from_square: int, to_square: int, promotion: int | None = None):
        self.from_square = from_square
        self.to_square = to_square
        self.promotion = promotion

    @classmethod
    def from_uci(cls, uci: str) -> "Move":
        from_sq = _parse_square(uci[0:2])
        to_sq = _parse_square(uci[2:4])
        promo = _PROMO_FROM_CHAR.get(uci[4].lower()) if len(uci) == 5 else None
        return cls(from_sq, to_sq, promo)

    def uci(self) -> str:
        s = _square_name(self.from_square) + _square_name(self.to_square)
        if self.promotion:
            s += _PROMO_CHARS[self.promotion]
        return s

    def __eq__(self, other):
        if not isinstance(other, Move):
            return NotImplemented
        return (
            self.from_square == other.from_square
            and self.to_square == other.to_square
            and self.promotion == other.promotion
        )

    def __hash__(self):
        return hash((self.from_square, self.to_square, self.promotion))

    def __repr__(self):
        return f"Move.from_uci('{self.uci()}')"


# ---------------------------------------------------------------------------
# Board
# ---------------------------------------------------------------------------
_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"

_CHAR_TO_PIECE_TYPE = {
    "p": PAWN, "n": KNIGHT, "b": BISHOP, "r": ROOK, "q": QUEEN, "k": KING,
}

# Pre-computed knight offsets (dr, df)
_KNIGHT_OFFSETS = [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]
# King offsets
_KING_OFFSETS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
# Diagonal directions (bishop / queen)
_DIAG_DIRS = [(-1, -1), (-1, 1), (1, -1), (1, 1)]
# Orthogonal directions (rook / queen)
_ORTHO_DIRS = [(-1, 0), (1, 0), (0, -1), (0, 1)]


class _UndoState:
    """Snapshot of everything that changes on a move."""
    __slots__ = ("board", "turn", "castling", "ep_square", "halfmove", "fullmove")

    def __init__(self, board, turn, castling, ep_square, halfmove, fullmove):
        self.board = board
        self.turn = turn
        self.castling = castling
        self.ep_square = ep_square
        self.halfmove = halfmove
        self.fullmove = fullmove


class Board:
    # -----------------------------------------------------------------
    # Construction
    # -----------------------------------------------------------------
    def __init__(self, fen: str | None = None):
        self._board: list[Piece | None] = [None] * 64
        self.turn: bool = WHITE
        self._castling = [False, False, False, False]  # K, Q, k, q
        self._ep_square: int | None = None
        self._halfmove_clock: int = 0
        self._fullmove_number: int = 1

        self.move_stack: list[Move] = []
        self._undo_stack: list[_UndoState] = []
        self._position_counts: dict[str, int] = {}

        self._set_fen(fen or _STARTING_FEN)
        self._record_position()

    # -----------------------------------------------------------------
    # FEN
    # -----------------------------------------------------------------
    def _set_fen(self, fen: str):
        parts = fen.split()
        if len(parts) < 2:
            raise ValueError(f"Invalid FEN: {fen}")

        # 1) piece placement
        self._board = [None] * 64
        rank, file = 7, 0
        for ch in parts[0]:
            if ch == "/":
                rank -= 1
                file = 0
            elif ch.isdigit():
                file += int(ch)
            else:
                color = WHITE if ch.isupper() else BLACK
                lc = ch.lower()
                if lc not in _CHAR_TO_PIECE_TYPE:
                    raise ValueError(f"Invalid piece character in FEN: '{ch}'")
                pt = _CHAR_TO_PIECE_TYPE[lc]
                self._board[rank * 8 + file] = Piece(pt, color)
                file += 1

        # 2) active colour
        self.turn = WHITE if parts[1] == "w" else BLACK

        # 3) castling availability
        self._castling = [False, False, False, False]
        if len(parts) > 2 and parts[2] != "-":
            for ch in parts[2]:
                idx = "KQkq".index(ch)
                self._castling[idx] = True

        # 4) en-passant target
        self._ep_square = None
        if len(parts) > 3 and parts[3] != "-":
            self._ep_square = _parse_square(parts[3])

        # 5-6) clocks
        self._halfmove_clock = int(parts[4]) if len(parts) > 4 else 0
        self._fullmove_number = int(parts[5]) if len(parts) > 5 else 1

    def fen(self) -> str:
        # piece placement
        rows: list[str] = []
        for rank in range(7, -1, -1):
            row = ""
            empty = 0
            for file in range(8):
                p = self._board[rank * 8 + file]
                if p is None:
                    empty += 1
                else:
                    if empty:
                        row += str(empty)
                        empty = 0
                    row += p.symbol()
            if empty:
                row += str(empty)
            rows.append(row)

        placement = "/".join(rows)
        color = "w" if self.turn == WHITE else "b"

        castling = ""
        for i, ch in enumerate("KQkq"):
            if self._castling[i]:
                castling += ch
        castling = castling or "-"

        ep = _square_name(self._ep_square) if self._ep_square is not None else "-"

        return f"{placement} {color} {castling} {ep} {self._halfmove_clock} {self._fullmove_number}"

    # -----------------------------------------------------------------
    # Piece queries
    # -----------------------------------------------------------------
    def piece_at(self, sq: int) -> Piece | None:
        return self._board[sq]

    def king(self, color: bool) -> int | None:
        for sq in SQUARES:
            p = self._board[sq]
            if p is not None and p.piece_type == KING and p.color == color:
                return sq
        return None

    # -----------------------------------------------------------------
    # Attack detection
    # -----------------------------------------------------------------
    def _is_attacked_by(self, sq: int, color: bool) -> bool:
        """Return True if *sq* is attacked by any piece of *color*."""
        r = _square_rank(sq)
        f = _square_file(sq)

        # --- pawns ---
        pawn_dr = -1 if color == WHITE else 1  # rank direction toward the attacker
        pr = r + pawn_dr
        if 0 <= pr <= 7:
            for df in (-1, 1):
                pf = f + df
                if 0 <= pf <= 7:
                    p = self._board[pr * 8 + pf]
                    if p is not None and p.piece_type == PAWN and p.color == color:
                        return True

        # --- knights ---
        for dr, df in _KNIGHT_OFFSETS:
            nr, nf = r + dr, f + df
            if 0 <= nr <= 7 and 0 <= nf <= 7:
                p = self._board[nr * 8 + nf]
                if p is not None and p.piece_type == KNIGHT and p.color == color:
                    return True

        # --- king ---
        for dr, df in _KING_OFFSETS:
            kr, kf = r + dr, f + df
            if 0 <= kr <= 7 and 0 <= kf <= 7:
                p = self._board[kr * 8 + kf]
                if p is not None and p.piece_type == KING and p.color == color:
                    return True

        # --- sliding: diagonals (bishop / queen) ---
        for dr, df in _DIAG_DIRS:
            sr, sf = r + dr, f + df
            while 0 <= sr <= 7 and 0 <= sf <= 7:
                p = self._board[sr * 8 + sf]
                if p is not None:
                    if p.color == color and p.piece_type in (BISHOP, QUEEN):
                        return True
                    break
                sr += dr
                sf += df

        # --- sliding: orthogonal (rook / queen) ---
        for dr, df in _ORTHO_DIRS:
            sr, sf = r + dr, f + df
            while 0 <= sr <= 7 and 0 <= sf <= 7:
                p = self._board[sr * 8 + sf]
                if p is not None:
                    if p.color == color and p.piece_type in (ROOK, QUEEN):
                        return True
                    break
                sr += dr
                sf += df

        return False

    # -----------------------------------------------------------------
    # Pseudo-legal move generation
    # -----------------------------------------------------------------
    def _gen_pseudo_legal(self) -> list[Move]:
        moves: list[Move] = []
        board = self._board
        turn = self.turn

        for sq in SQUARES:
            piece = board[sq]
            if piece is None or piece.color != turn:
                continue

            r = _square_rank(sq)
            f = _square_file(sq)
            pt = piece.piece_type

            if pt == PAWN:
                self._gen_pawn_moves(moves, sq, r, f, turn)
            elif pt == KNIGHT:
                self._gen_knight_moves(moves, sq, r, f, turn)
            elif pt == BISHOP:
                self._gen_sliding_moves(moves, sq, r, f, turn, _DIAG_DIRS)
            elif pt == ROOK:
                self._gen_sliding_moves(moves, sq, r, f, turn, _ORTHO_DIRS)
            elif pt == QUEEN:
                self._gen_sliding_moves(moves, sq, r, f, turn, _DIAG_DIRS + _ORTHO_DIRS)
            elif pt == KING:
                self._gen_king_moves(moves, sq, r, f, turn)

        return moves

    def _gen_pawn_moves(self, moves, sq, r, f, color):
        direction = 1 if color == WHITE else -1
        start_rank = 1 if color == WHITE else 6
        promo_rank = 7 if color == WHITE else 0
        board = self._board

        # single push
        tr = r + direction
        if 0 <= tr <= 7:
            tsq = tr * 8 + f
            if board[tsq] is None:
                if tr == promo_rank:
                    for pt in (QUEEN, ROOK, BISHOP, KNIGHT):
                        moves.append(Move(sq, tsq, pt))
                else:
                    moves.append(Move(sq, tsq))

                    # double push
                    if r == start_rank:
                        tsq2 = (r + 2 * direction) * 8 + f
                        if board[tsq2] is None:
                            moves.append(Move(sq, tsq2))

            # captures (including en-passant)
            for df in (-1, 1):
                tf = f + df
                if 0 <= tf <= 7:
                    csq = tr * 8 + tf
                    target = board[csq]
                    if target is not None and target.color != color:
                        if tr == promo_rank:
                            for pt in (QUEEN, ROOK, BISHOP, KNIGHT):
                                moves.append(Move(sq, csq, pt))
                        else:
                            moves.append(Move(sq, csq))
                    elif csq == self._ep_square:
                        moves.append(Move(sq, csq))

    def _gen_knight_moves(self, moves, sq, r, f, color):
        board = self._board
        for dr, df in _KNIGHT_OFFSETS:
            tr, tf = r + dr, f + df
            if 0 <= tr <= 7 and 0 <= tf <= 7:
                tsq = tr * 8 + tf
                t = board[tsq]
                if t is None or t.color != color:
                    moves.append(Move(sq, tsq))

    def _gen_sliding_moves(self, moves, sq, r, f, color, directions):
        board = self._board
        for dr, df in directions:
            sr, sf = r + dr, f + df
            while 0 <= sr <= 7 and 0 <= sf <= 7:
                tsq = sr * 8 + sf
                t = board[tsq]
                if t is None:
                    moves.append(Move(sq, tsq))
                elif t.color != color:
                    moves.append(Move(sq, tsq))
                    break
                else:
                    break
                sr += dr
                sf += df

    def _gen_king_moves(self, moves, sq, r, f, color):
        board = self._board
        opp = not color

        # normal moves
        for dr, df in _KING_OFFSETS:
            tr, tf = r + dr, f + df
            if 0 <= tr <= 7 and 0 <= tf <= 7:
                tsq = tr * 8 + tf
                t = board[tsq]
                if t is None or t.color != color:
                    moves.append(Move(sq, tsq))

        # castling
        if color == WHITE and sq == 4:
            # kingside  (e1 -> g1)
            if self._castling[0]:
                if board[5] is None and board[6] is None:
                    if (not self._is_attacked_by(4, opp)
                            and not self._is_attacked_by(5, opp)
                            and not self._is_attacked_by(6, opp)):
                        moves.append(Move(4, 6))
            # queenside (e1 -> c1)
            if self._castling[1]:
                if board[1] is None and board[2] is None and board[3] is None:
                    if (not self._is_attacked_by(4, opp)
                            and not self._is_attacked_by(3, opp)
                            and not self._is_attacked_by(2, opp)):
                        moves.append(Move(4, 2))

        elif color == BLACK and sq == 60:
            # kingside  (e8 -> g8)
            if self._castling[2]:
                if board[61] is None and board[62] is None:
                    if (not self._is_attacked_by(60, opp)
                            and not self._is_attacked_by(61, opp)
                            and not self._is_attacked_by(62, opp)):
                        moves.append(Move(60, 62))
            # queenside (e8 -> c8)
            if self._castling[3]:
                if board[57] is None and board[58] is None and board[59] is None:
                    if (not self._is_attacked_by(60, opp)
                            and not self._is_attacked_by(59, opp)
                            and not self._is_attacked_by(58, opp)):
                        moves.append(Move(60, 58))

    # -----------------------------------------------------------------
    # Legality filter
    # -----------------------------------------------------------------
    def _is_legal(self, move: Move) -> bool:
        """True if *move* doesn't leave the side-to-move's king in check."""
        self._raw_push(move)
        # after _raw_push, turn has flipped; our king colour is `not self.turn`
        king_sq = self.king(not self.turn)
        legal = king_sq is not None and not self._is_attacked_by(king_sq, self.turn)
        self._raw_pop()
        return legal

    # -----------------------------------------------------------------
    # Legal moves (lazy iterable)
    # -----------------------------------------------------------------
    @property
    def legal_moves(self) -> "_LegalMoves":
        return _LegalMoves(self)

    # -----------------------------------------------------------------
    # Making / unmaking moves (internal)
    # -----------------------------------------------------------------
    def _snapshot(self) -> _UndoState:
        return _UndoState(
            board=self._board[:],
            turn=self.turn,
            castling=self._castling[:],
            ep_square=self._ep_square,
            halfmove=self._halfmove_clock,
            fullmove=self._fullmove_number,
        )

    def _restore(self, state: _UndoState):
        self._board = state.board
        self.turn = state.turn
        self._castling = state.castling
        self._ep_square = state.ep_square
        self._halfmove_clock = state.halfmove
        self._fullmove_number = state.fullmove

    def _raw_push(self, move: Move):
        """Apply *move* to the board, saving undo state.  No move_stack update."""
        self._undo_stack.append(self._snapshot())

        piece = self._board[move.from_square]
        captured = self._board[move.to_square]
        is_ep = piece.piece_type == PAWN and move.to_square == self._ep_square

        # move piece
        self._board[move.to_square] = piece
        self._board[move.from_square] = None

        # en-passant capture
        if is_ep:
            cap_sq = move.to_square + (-8 if piece.color == WHITE else 8)
            self._board[cap_sq] = None

        # promotion
        if move.promotion:
            self._board[move.to_square] = Piece(move.promotion, piece.color)

        # castling rook movement
        if piece.piece_type == KING:
            diff = move.to_square - move.from_square
            if diff == 2:  # kingside
                rook_from = move.from_square + 3
                rook_to = move.from_square + 1
                self._board[rook_to] = self._board[rook_from]
                self._board[rook_from] = None
            elif diff == -2:  # queenside
                rook_from = move.from_square - 4
                rook_to = move.from_square - 1
                self._board[rook_to] = self._board[rook_from]
                self._board[rook_from] = None

        # update en-passant square
        if piece.piece_type == PAWN and abs(move.to_square - move.from_square) == 16:
            self._ep_square = (move.from_square + move.to_square) // 2
        else:
            self._ep_square = None

        # update castling rights
        if piece.piece_type == KING:
            if piece.color == WHITE:
                self._castling[0] = False  # K
                self._castling[1] = False  # Q
            else:
                self._castling[2] = False  # k
                self._castling[3] = False  # q

        # rook moved or captured → revoke relevant right
        _ROOK_CORNERS = {0: 1, 7: 0, 56: 3, 63: 2}  # sq -> castling index
        for sq in (move.from_square, move.to_square):
            if sq in _ROOK_CORNERS:
                self._castling[_ROOK_CORNERS[sq]] = False

        # halfmove clock
        if piece.piece_type == PAWN or captured is not None or is_ep:
            self._halfmove_clock = 0
        else:
            self._halfmove_clock += 1

        # fullmove number
        if self.turn == BLACK:
            self._fullmove_number += 1

        self.turn = not self.turn

    def _raw_pop(self):
        """Undo the last _raw_push."""
        self._restore(self._undo_stack.pop())

    # -----------------------------------------------------------------
    # Public push / pop / peek
    # -----------------------------------------------------------------
    def push(self, move: Move):
        self._raw_push(move)
        self.move_stack.append(move)
        self._record_position()

    def pop(self) -> Move:
        if not self.move_stack:
            raise IndexError("pop from empty move stack")
        # decrement position count for the position we're leaving
        key = self._position_key()
        cnt = self._position_counts.get(key, 1) - 1
        if cnt <= 0:
            self._position_counts.pop(key, None)
        else:
            self._position_counts[key] = cnt

        move = self.move_stack.pop()
        self._raw_pop()
        return move

    def peek(self) -> Move:
        if not self.move_stack:
            raise IndexError("peek from empty move stack")
        return self.move_stack[-1]

    # -----------------------------------------------------------------
    # Position counting (repetition detection)
    # -----------------------------------------------------------------
    def _position_key(self) -> str:
        parts = self.fen().split()
        return " ".join(parts[:4])

    def _record_position(self):
        key = self._position_key()
        self._position_counts[key] = self._position_counts.get(key, 0) + 1

    # -----------------------------------------------------------------
    # Check / game-over queries
    # -----------------------------------------------------------------
    def is_check(self) -> bool:
        king_sq = self.king(self.turn)
        return king_sq is not None and self._is_attacked_by(king_sq, not self.turn)

    def is_checkmate(self) -> bool:
        return self.is_check() and self._has_no_legal_moves()

    def is_stalemate(self) -> bool:
        return not self.is_check() and self._has_no_legal_moves()

    def _has_no_legal_moves(self) -> bool:
        for m in self._gen_pseudo_legal():
            if self._is_legal(m):
                return False
        return True

    def is_insufficient_material(self) -> bool:
        pieces: list[tuple[int, Piece]] = []
        for sq in SQUARES:
            p = self._board[sq]
            if p is not None:
                pieces.append((sq, p))

        # K vs K
        if len(pieces) == 2:
            return True

        # K + minor vs K
        if len(pieces) == 3:
            for _, p in pieces:
                if p.piece_type in (KNIGHT, BISHOP):
                    return True

        # K+B vs K+B with same-coloured bishops
        if len(pieces) == 4:
            bishops = [(sq, p) for sq, p in pieces if p.piece_type == BISHOP]
            if len(bishops) == 2:
                c1 = (_square_rank(bishops[0][0]) + _square_file(bishops[0][0])) & 1
                c2 = (_square_rank(bishops[1][0]) + _square_file(bishops[1][0])) & 1
                if c1 == c2:
                    return True

        return False

    def is_seventyfive_moves(self) -> bool:
        return self._halfmove_clock >= 150

    def is_fivefold_repetition(self) -> bool:
        return self._position_counts.get(self._position_key(), 0) >= 5

    def is_game_over(self) -> bool:
        return (
            self.is_checkmate()
            or self.is_stalemate()
            or self.is_insufficient_material()
            or self.is_seventyfive_moves()
            or self.is_fivefold_repetition()
        )

    # -----------------------------------------------------------------
    # SAN notation
    # -----------------------------------------------------------------
    def san(self, move: Move) -> str:
        piece = self._board[move.from_square]
        if piece is None:
            return move.uci()

        captured = self._board[move.to_square]
        is_ep = piece.piece_type == PAWN and move.to_square == self._ep_square
        is_capture = captured is not None or is_ep

        # castling
        if piece.piece_type == KING and abs(move.to_square - move.from_square) == 2:
            san_str = "O-O" if move.to_square > move.from_square else "O-O-O"
        else:
            san_str = self._build_san(piece, move, is_capture)

        # check / checkmate suffix
        self._raw_push(move)
        if self.is_checkmate():
            san_str += "#"
        elif self.is_check():
            san_str += "+"
        self._raw_pop()

        return san_str

    def _build_san(self, piece: Piece, move: Move, is_capture: bool) -> str:
        if piece.piece_type == PAWN:
            s = ""
            if is_capture:
                s = _FILE_NAMES[_square_file(move.from_square)] + "x"
            s += _square_name(move.to_square)
            if move.promotion:
                s += "=" + _PIECE_SYMBOLS[move.promotion].upper()
            return s

        letter = _PIECE_SYMBOLS[piece.piece_type].upper()
        disambig = self._disambiguate(piece, move)
        x = "x" if is_capture else ""
        return letter + disambig + x + _square_name(move.to_square)

    def _disambiguate(self, piece: Piece, move: Move) -> str:
        dominated_file = False
        dominated_rank = False
        dominated_both = False

        for m in self._gen_pseudo_legal():
            if m.from_square == move.from_square:
                continue
            p = self._board[m.from_square]
            if (
                p is not None
                and p.piece_type == piece.piece_type
                and p.color == piece.color
                and m.to_square == move.to_square
                and self._is_legal(m)
            ):
                if _square_file(m.from_square) == _square_file(move.from_square):
                    dominated_file = True
                if _square_rank(m.from_square) == _square_rank(move.from_square):
                    dominated_rank = True
                dominated_both = True

        if not dominated_both:
            return ""
        if not dominated_file:
            return _FILE_NAMES[_square_file(move.from_square)]
        if not dominated_rank:
            return str(_square_rank(move.from_square) + 1)
        return _square_name(move.from_square)


# ---------------------------------------------------------------------------
# Legal-move list wrapper
# ---------------------------------------------------------------------------
class _LegalMoves:
    """Lazy iterable that mimics python-chess ``board.legal_moves``."""

    def __init__(self, board: Board):
        self._board = board
        self._cache: list[Move] | None = None

    def _generate(self) -> list[Move]:
        if self._cache is None:
            self._cache = [m for m in self._board._gen_pseudo_legal() if self._board._is_legal(m)]
        return self._cache

    def __iter__(self):
        return iter(self._generate())

    def __contains__(self, move):
        return move in self._generate()

    def __len__(self):
        return len(self._generate())

    def __bool__(self):
        # short-circuit: stop at first legal move
        for m in self._board._gen_pseudo_legal():
            if self._board._is_legal(m):
                return True
        return False
