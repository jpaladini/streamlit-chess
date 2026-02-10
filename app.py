import streamlit as st
import chess
import csv
import io
from datetime import datetime

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Chess", page_icon="♟", layout="wide")

# ---------------------------------------------------------------------------
# Unicode piece map & square colours
# ---------------------------------------------------------------------------
PIECE_UNICODE = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}

LIGHT_SQ = "#f0d9b5"
DARK_SQ = "#b58863"
SELECTED_SQ = "#7fc97f"
LEGAL_MOVE_SQ = "#aad576"
LAST_MOVE_FROM = "#cdd26a80"
LAST_MOVE_TO = "#cdd26a80"

# ---------------------------------------------------------------------------
# Session state helpers
# ---------------------------------------------------------------------------

def _init_state():
    """Ensure every session-state key exists."""
    if "board" not in st.session_state:
        st.session_state.board = chess.Board()
    if "move_history" not in st.session_state:
        st.session_state.move_history = []  # list of UCI strings
    if "selected_square" not in st.session_state:
        st.session_state.selected_square = None
    if "white_player" not in st.session_state:
        st.session_state.white_player = "Player 1"
    if "black_player" not in st.session_state:
        st.session_state.black_player = "Player 2"
    if "game_name" not in st.session_state:
        st.session_state.game_name = ""
    if "flip_board" not in st.session_state:
        st.session_state.flip_board = False
    if "promotion_pending" not in st.session_state:
        st.session_state.promotion_pending = None  # (from_sq, to_sq) awaiting promotion choice


_init_state()

# Shortcuts
board: chess.Board = st.session_state.board


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def reset_game():
    st.session_state.board = chess.Board()
    st.session_state.move_history = []
    st.session_state.selected_square = None
    st.session_state.promotion_pending = None


def try_make_move(from_sq: int, to_sq: int, promotion: chess.PieceType | None = None):
    """Attempt to push a move. Returns True on success."""
    b: chess.Board = st.session_state.board
    move = chess.Move(from_sq, to_sq, promotion=promotion)
    if move in b.legal_moves:
        san = b.san(move)
        b.push(move)
        st.session_state.move_history.append(
            {"uci": move.uci(), "san": san}
        )
        st.session_state.selected_square = None
        st.session_state.promotion_pending = None
        return True
    return False


def needs_promotion(from_sq: int, to_sq: int) -> bool:
    """Check if a pawn move to the last rank requires promotion."""
    b: chess.Board = st.session_state.board
    piece = b.piece_at(from_sq)
    if piece is None or piece.piece_type != chess.PAWN:
        return False
    target_rank = chess.square_rank(to_sq)
    if (piece.color == chess.WHITE and target_rank == 7) or (
        piece.color == chess.BLACK and target_rank == 0
    ):
        # Verify at least one promotion variant is legal
        for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT]:
            if chess.Move(from_sq, to_sq, promotion=pt) in b.legal_moves:
                return True
    return False


def undo_move():
    b: chess.Board = st.session_state.board
    if b.move_stack:
        b.pop()
        st.session_state.move_history.pop()
        st.session_state.selected_square = None
        st.session_state.promotion_pending = None


def square_name(sq: int) -> str:
    return chess.square_name(sq)


def get_legal_target_squares(sq: int) -> set[int]:
    """Return set of target squares the piece on *sq* can legally move to."""
    b: chess.Board = st.session_state.board
    targets: set[int] = set()
    for m in b.legal_moves:
        if m.from_square == sq:
            targets.add(m.to_square)
    return targets


def last_move_squares() -> tuple[int | None, int | None]:
    b: chess.Board = st.session_state.board
    if b.move_stack:
        m = b.peek()
        return m.from_square, m.to_square
    return None, None


# ---------------------------------------------------------------------------
# CSV export / import
# ---------------------------------------------------------------------------

def game_to_csv() -> str:
    """Serialise current game to CSV string."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "move_number", "uci", "san", "fen_after",
        "white_player", "black_player", "game_name", "timestamp",
    ])
    # Replay moves to capture FEN after each move
    replay = chess.Board()
    for i, entry in enumerate(st.session_state.move_history):
        replay.push(chess.Move.from_uci(entry["uci"]))
        writer.writerow([
            i + 1,
            entry["uci"],
            entry["san"],
            replay.fen(),
            st.session_state.white_player,
            st.session_state.black_player,
            st.session_state.game_name,
            datetime.now().isoformat(),
        ])
    return buf.getvalue()


def load_game_from_csv(csv_text: str):
    """Restore a game from a previously exported CSV."""
    reader = csv.DictReader(io.StringIO(csv_text))
    new_board = chess.Board()
    history = []
    white = "Player 1"
    black = "Player 2"
    name = ""
    for row in reader:
        uci = row["uci"]
        san = row["san"]
        move = chess.Move.from_uci(uci)
        new_board.push(move)
        history.append({"uci": uci, "san": san})
        white = row.get("white_player", white)
        black = row.get("black_player", black)
        name = row.get("game_name", name)

    st.session_state.board = new_board
    st.session_state.move_history = history
    st.session_state.selected_square = None
    st.session_state.promotion_pending = None
    st.session_state.white_player = white
    st.session_state.black_player = black
    st.session_state.game_name = name


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
    /* board wrapper */
    .chess-board {
        display: grid;
        grid-template-columns: repeat(8, 1fr);
        max-width: 560px;
        border: 3px solid #333;
        border-radius: 4px;
        overflow: hidden;
        box-shadow: 0 4px 24px rgba(0,0,0,.35);
    }
    .chess-sq {
        aspect-ratio: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 2.6rem;
        user-select: none;
        position: relative;
    }
    .chess-sq .coord {
        position: absolute;
        font-size: .55rem;
        opacity: .55;
        font-weight: 700;
        font-family: monospace;
    }
    .chess-sq .coord-file { bottom: 2px; right: 4px; }
    .chess-sq .coord-rank { top: 2px; left: 4px; }

    /* move list */
    .move-list {
        font-family: 'SF Mono', 'Fira Code', monospace;
        font-size: .85rem;
        max-height: 420px;
        overflow-y: auto;
        padding: .25rem .5rem;
    }
    .move-list .move-num {
        color: #999;
        min-width: 2rem;
        display: inline-block;
    }

    /* status badge */
    .status-badge {
        display: inline-block;
        padding: .25rem .75rem;
        border-radius: 999px;
        font-weight: 600;
        font-size: .9rem;
    }
    .status-white { background: #fff; color: #222; border: 2px solid #ccc; }
    .status-black { background: #333; color: #fff; border: 2px solid #333; }
    .status-end   { background: #e74c3c; color: #fff; }

    /* hide default streamlit button styling on board squares */
    div[data-testid="stHorizontalBlock"] button {
        padding: 0 !important;
        margin: 0 !important;
    }
</style>
"""

# ---------------------------------------------------------------------------
# Board rendering (pure HTML – click handled via st.columns + buttons)
# ---------------------------------------------------------------------------

def render_board():
    """Draw the board using an 8×8 grid of Streamlit buttons."""
    b: chess.Board = st.session_state.board
    selected = st.session_state.selected_square
    legal_targets = get_legal_target_squares(selected) if selected is not None else set()
    last_from, last_to = last_move_squares()
    flipped = st.session_state.flip_board

    ranks = range(7, -1, -1) if not flipped else range(8)
    files = range(8) if not flipped else range(7, -1, -1)

    for rank in ranks:
        cols = st.columns(8, gap="small")
        for idx, file in enumerate(files):
            sq = chess.square(file, rank)
            piece = b.piece_at(sq)

            # Determine background colour
            is_light = (file + rank) % 2 == 1
            if sq == selected:
                bg = SELECTED_SQ
            elif sq in legal_targets:
                bg = LEGAL_MOVE_SQ
            elif sq == last_from or sq == last_to:
                bg = LAST_MOVE_FROM if sq == last_from else LAST_MOVE_TO
            else:
                bg = LIGHT_SQ if is_light else DARK_SQ

            label = PIECE_UNICODE.get(piece.symbol(), "") if piece else ""
            # Use a small dot for empty legal-target squares
            if sq in legal_targets and not piece:
                label = "•"

            with cols[idx]:
                if st.button(
                    label,
                    key=f"sq_{sq}",
                    use_container_width=True,
                    help=square_name(sq),
                ):
                    handle_square_click(sq)
                # Inject coloured background via markdown trick
                st.markdown(
                    f"""<style>
                    div[data-testid="stVerticalBlock"] button[kind="secondary"][key="sq_{sq}"] {{
                        background-color: {bg} !important;
                    }}
                    </style>""",
                    unsafe_allow_html=True,
                )


def handle_square_click(sq: int):
    """State-machine for piece selection & move execution."""
    b: chess.Board = st.session_state.board
    selected = st.session_state.selected_square

    if selected is None:
        # Select a piece of the current player
        piece = b.piece_at(sq)
        if piece and piece.color == b.turn:
            st.session_state.selected_square = sq
    else:
        if sq == selected:
            # Deselect
            st.session_state.selected_square = None
        else:
            # Try to move
            if needs_promotion(selected, sq):
                st.session_state.promotion_pending = (selected, sq)
            else:
                if not try_make_move(selected, sq):
                    # Clicked on own piece → reselect
                    piece = b.piece_at(sq)
                    if piece and piece.color == b.turn:
                        st.session_state.selected_square = sq
                    else:
                        st.session_state.selected_square = None


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def game_status_html() -> str:
    b: chess.Board = st.session_state.board
    if b.is_checkmate():
        winner = "Black" if b.turn == chess.WHITE else "White"
        return f'<span class="status-badge status-end">Checkmate — {winner} wins!</span>'
    if b.is_stalemate():
        return '<span class="status-badge status-end">Stalemate — Draw</span>'
    if b.is_insufficient_material():
        return '<span class="status-badge status-end">Draw — Insufficient material</span>'
    if b.is_seventyfive_moves():
        return '<span class="status-badge status-end">Draw — 75-move rule</span>'
    if b.is_fivefold_repetition():
        return '<span class="status-badge status-end">Draw — Fivefold repetition</span>'
    if b.is_check():
        if b.turn == chess.WHITE:
            return '<span class="status-badge status-white">White to move — Check!</span>'
        return '<span class="status-badge status-black">Black to move — Check!</span>'
    if b.turn == chess.WHITE:
        return '<span class="status-badge status-white">White to move</span>'
    return '<span class="status-badge status-black">Black to move</span>'


def move_list_html() -> str:
    history = st.session_state.move_history
    if not history:
        return "<em>No moves yet.</em>"
    lines = []
    for i in range(0, len(history), 2):
        num = i // 2 + 1
        white_san = history[i]["san"]
        black_san = history[i + 1]["san"] if i + 1 < len(history) else ""
        lines.append(
            f'<span class="move-num">{num}.</span> {white_san}  {black_san}'
        )
    return "<br>".join(lines)


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# Title
st.markdown("## ♟ Streamlit Chess")

col_board, col_panel = st.columns([3, 2], gap="large")

with col_board:
    st.markdown(game_status_html(), unsafe_allow_html=True)
    st.write("")

    # Promotion dialog (if pending)
    if st.session_state.promotion_pending:
        from_sq, to_sq = st.session_state.promotion_pending
        st.info("Choose promotion piece:")
        pcols = st.columns(4)
        promo_map = {
            "Queen": chess.QUEEN,
            "Rook": chess.ROOK,
            "Bishop": chess.BISHOP,
            "Knight": chess.KNIGHT,
        }
        symbols = {"Queen": "♛", "Rook": "♜", "Bishop": "♝", "Knight": "♞"}
        for i, (name, pt) in enumerate(promo_map.items()):
            with pcols[i]:
                if st.button(f"{symbols[name]} {name}", key=f"promo_{name}"):
                    try_make_move(from_sq, to_sq, promotion=pt)
                    st.rerun()

    render_board()

    # Board controls
    bcols = st.columns(3)
    with bcols[0]:
        if st.button("↩ Undo", use_container_width=True):
            undo_move()
            st.rerun()
    with bcols[1]:
        if st.button("🔄 Flip Board", use_container_width=True):
            st.session_state.flip_board = not st.session_state.flip_board
            st.rerun()
    with bcols[2]:
        if st.button("🗑 New Game", use_container_width=True):
            reset_game()
            st.rerun()


with col_panel:
    # ----- Game info -----
    st.markdown("#### Game Info")
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.white_player = st.text_input(
            "White", value=st.session_state.white_player, key="inp_white"
        )
    with c2:
        st.session_state.black_player = st.text_input(
            "Black", value=st.session_state.black_player, key="inp_black"
        )
    st.session_state.game_name = st.text_input(
        "Game name (optional)", value=st.session_state.game_name, key="inp_name"
    )

    st.markdown("---")

    # ----- Move list -----
    st.markdown("#### Moves")
    st.markdown(
        f'<div class="move-list">{move_list_html()}</div>',
        unsafe_allow_html=True,
    )

    st.markdown("---")

    # ----- Export -----
    st.markdown("#### Export Game")
    csv_data = game_to_csv()
    if st.session_state.move_history:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chess_game_{timestamp}.csv"
        st.download_button(
            label="⬇ Download CSV",
            data=csv_data,
            file_name=filename,
            mime="text/csv",
            use_container_width=True,
        )
    else:
        st.caption("Make some moves first to export.")

    st.markdown("---")

    # ----- Import -----
    st.markdown("#### Import Game")
    uploaded = st.file_uploader(
        "Upload a previously exported CSV",
        type=["csv"],
        key="csv_upload",
    )
    if uploaded is not None:
        if st.button("📂 Load Game", use_container_width=True):
            try:
                csv_text = uploaded.getvalue().decode("utf-8")
                load_game_from_csv(csv_text)
                st.success("Game loaded successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Failed to load game: {e}")

    st.markdown("---")

    # ----- FEN -----
    st.markdown("#### FEN")
    st.code(st.session_state.board.fen(), language=None)

    fen_input = st.text_input("Load from FEN", key="fen_input")
    if fen_input:
        if st.button("Load FEN", use_container_width=True):
            try:
                new_board = chess.Board(fen_input)
                st.session_state.board = new_board
                st.session_state.move_history = []
                st.session_state.selected_square = None
                st.session_state.promotion_pending = None
                st.rerun()
            except ValueError as e:
                st.error(f"Invalid FEN: {e}")
