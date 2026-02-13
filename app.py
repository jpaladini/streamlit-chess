import streamlit as st
import streamlit.components.v1 as components
import chess
import csv
import io
import os
import json
import uuid
from datetime import datetime, timedelta

import db

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Chess", page_icon="♟", layout="wide")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
POLL_RATE_SECONDS = 2  # How often to check for opponent moves (adjustable)

# ---------------------------------------------------------------------------
# Custom board component (JS handles click-to-move, no page reloads)
# ---------------------------------------------------------------------------
_COMPONENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess_component")
_chess_board_func = components.declare_component("chess_board", path=_COMPONENT_DIR)


def chess_board_widget(data: dict, key: str = "_board_widget"):
    """Render the interactive chess board. Returns move dict or None."""
    return _chess_board_func(data=data, key=key, default=None)


# ---------------------------------------------------------------------------
# Piece maps & values
# ---------------------------------------------------------------------------
PIECE_UNICODE = {
    "P": "♙", "N": "♘", "B": "♗", "R": "♖", "Q": "♕", "K": "♔",
    "p": "♟", "n": "♞", "b": "♝", "r": "♜", "q": "♛", "k": "♚",
}

PIECE_VALUE = {
    chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3,
    chess.ROOK: 5, chess.QUEEN: 9,
}

# ---------------------------------------------------------------------------
# Database init (runs once per app lifecycle)
# ---------------------------------------------------------------------------

@st.cache_resource
def _init_database():
    db.init_db()
    db.cleanup_old_games(24)
    return True


_init_database()

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

def _init_state():
    defaults = {
        "board": chess.Board(),
        "move_history": [],
        "white_player": "Player 1",
        "black_player": "Player 2",
        "game_name": "",
        "flip_board": False,
        "_last_move_ts": None,
        # Multiplayer
        "_session_id": str(uuid.uuid4()),
        "game_mode": "local",      # "local" or "multiplayer"
        "game_id": None,            # 4-char code when in a multiplayer game
        "player_color": None,       # "white" or "black"
        "_last_db_ts": None,        # last processed DB timestamp
        "_opponent_connected": False,
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val


_init_state()

# ---------------------------------------------------------------------------
# Auto-reconnect from URL query params (?game=ABCD&color=white)
# ---------------------------------------------------------------------------
_qp = st.query_params
if _qp.get("id") and _qp.get("s") and not st.session_state.game_id:
    _rejoin_id = _qp["id"].upper()
    _rejoin_color = _qp["s"].lower()
    _rejoin_game = db.get_game(_rejoin_id)
    if _rejoin_game and _rejoin_color in ("white", "black"):
        db.update_player_session(_rejoin_id, _rejoin_color, st.session_state._session_id)
        st.session_state.game_mode = "multiplayer"
        st.session_state.game_id = _rejoin_id
        st.session_state.player_color = _rejoin_color
        st.session_state.flip_board = _rejoin_color == "black"
        st.session_state.board = chess.Board(_rejoin_game["fen"])
        st.session_state.move_history = json.loads(_rejoin_game["move_history"])
        st.session_state._last_db_ts = _rejoin_game["last_move_ts"]
        st.session_state.white_player = _rejoin_game["white_player"]
        st.session_state.black_player = _rejoin_game["black_player"]
        opp_key = "black_session" if _rejoin_color == "white" else "white_session"
        st.session_state._opponent_connected = bool(_rejoin_game.get(opp_key))

board: chess.Board = st.session_state.board

# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def reset_game():
    st.session_state.board = chess.Board()
    st.session_state.move_history = []


def make_move(move: chess.Move):
    b: chess.Board = st.session_state.board
    san = b.san(move)
    b.push(move)
    st.session_state.move_history.append({"uci": move.uci(), "san": san})

    # Sync to DB in multiplayer
    if st.session_state.game_mode == "multiplayer" and st.session_state.game_id:
        ts = db.update_game_move(
            st.session_state.game_id,
            b.fen(),
            json.dumps(st.session_state.move_history),
        )
        st.session_state._last_db_ts = ts


def undo_move():
    b: chess.Board = st.session_state.board
    if b.move_stack:
        b.pop()
        st.session_state.move_history.pop()


def is_my_turn() -> bool:
    """Can the current session move right now?"""
    if st.session_state.game_mode == "local":
        return True
    b: chess.Board = st.session_state.board
    color = st.session_state.player_color
    if color == "white" and b.turn == chess.WHITE:
        return True
    if color == "black" and b.turn == chess.BLACK:
        return True
    return False


def get_captured_pieces() -> tuple[list[str], list[str]]:
    initial = chess.Board()
    current = st.session_state.board

    def count_pieces(b: chess.Board):
        white, black = {}, {}
        for sq in chess.SQUARES:
            p = b.piece_at(sq)
            if p:
                d = white if p.color == chess.WHITE else black
                d[p.piece_type] = d.get(p.piece_type, 0) + 1
        return white, black

    iw, ib = count_pieces(initial)
    cw, cb = count_pieces(current)

    captured_white: list[str] = []
    captured_black: list[str] = []
    for pt in [chess.QUEEN, chess.ROOK, chess.BISHOP, chess.KNIGHT, chess.PAWN]:
        for _ in range(iw.get(pt, 0) - cw.get(pt, 0)):
            captured_white.append(PIECE_UNICODE[chess.Piece(pt, chess.WHITE).symbol()])
        for _ in range(ib.get(pt, 0) - cb.get(pt, 0)):
            captured_black.append(PIECE_UNICODE[chess.Piece(pt, chess.BLACK).symbol()])

    return captured_white, captured_black


def material_advantage() -> int:
    brd: chess.Board = st.session_state.board
    white_mat = 0
    black_mat = 0
    for sq in chess.SQUARES:
        piece = brd.piece_at(sq)
        if piece and piece.piece_type != chess.KING:
            val = PIECE_VALUE.get(piece.piece_type, 0)
            if piece.color == chess.WHITE:
                white_mat += val
            else:
                black_mat += val
    return white_mat - black_mat


# ---------------------------------------------------------------------------
# Board data for component
# ---------------------------------------------------------------------------

def get_board_data() -> dict:
    b: chess.Board = st.session_state.board

    position = {}
    for sq in chess.SQUARES:
        p = b.piece_at(sq)
        if p:
            position[sq] = p.symbol()

    legal_by_sq: dict[int, set[int]] = {}
    for m in b.legal_moves:
        legal_by_sq.setdefault(m.from_square, set()).add(m.to_square)
    legal_moves_data = {k: list(v) for k, v in legal_by_sq.items()}

    last_move = None
    if b.move_stack:
        lm = b.peek()
        last_move = [lm.from_square, lm.to_square]

    check_sq = None
    if b.is_check():
        check_sq = b.king(b.turn)

    return {
        "position": position,
        "legalMoves": legal_moves_data,
        "lastMove": last_move,
        "checkSquare": check_sq,
        "flipped": st.session_state.flip_board,
        "turn": "w" if b.turn == chess.WHITE else "b",
        "gameOver": b.is_game_over(),
        "myTurn": is_my_turn(),
    }


# ---------------------------------------------------------------------------
# CSV export / import
# ---------------------------------------------------------------------------

def game_to_csv() -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "move_number", "uci", "san", "fen_after",
        "white_player", "black_player", "game_name", "timestamp",
    ])
    replay = chess.Board()
    for i, entry in enumerate(st.session_state.move_history):
        replay.push(chess.Move.from_uci(entry["uci"]))
        writer.writerow([
            i + 1, entry["uci"], entry["san"], replay.fen(),
            st.session_state.white_player, st.session_state.black_player,
            st.session_state.game_name, datetime.now().isoformat(),
        ])
    return buf.getvalue()


def load_game_from_csv(csv_text: str):
    reader = csv.DictReader(io.StringIO(csv_text))
    new_board = chess.Board()
    history: list[dict] = []
    white = "Player 1"
    black = "Player 2"
    name = ""
    for row in reader:
        uci = row["uci"]
        san = row["san"]
        new_board.push(chess.Move.from_uci(uci))
        history.append({"uci": uci, "san": san})
        white = row.get("white_player", white)
        black = row.get("black_player", black)
        name = row.get("game_name", name)
    st.session_state.board = new_board
    st.session_state.move_history = history
    st.session_state.white_player = white
    st.session_state.black_player = black
    st.session_state.game_name = name


# ---------------------------------------------------------------------------
# Multiplayer polling (auto-detects opponent moves)
# ---------------------------------------------------------------------------

@st.fragment(run_every=timedelta(seconds=POLL_RATE_SECONDS))
def poll_for_moves():
    """Periodically check DB for opponent's moves or new connections."""
    if st.session_state.game_mode != "multiplayer" or not st.session_state.game_id:
        return

    game = db.get_game(st.session_state.game_id)
    if not game:
        return

    # Detect opponent joining
    opp_key = "black_session" if st.session_state.player_color == "white" else "white_session"
    if game.get(opp_key) and not st.session_state.get("_opponent_connected"):
        st.session_state._opponent_connected = True
        st.rerun(scope="app")

    # Detect new moves
    db_ts = game["last_move_ts"]
    if db_ts is not None and db_ts != st.session_state.get("_last_db_ts"):
        st.session_state._last_db_ts = db_ts
        st.session_state.board = chess.Board(game["fen"])
        st.session_state.move_history = json.loads(game["move_history"])
        st.rerun(scope="app")


# ---------------------------------------------------------------------------
# Status & move list HTML
# ---------------------------------------------------------------------------

def game_status_html() -> str:
    b: chess.Board = st.session_state.board
    if b.is_checkmate():
        winner = "Black" if b.turn == chess.WHITE else "White"
        return f'<div class="turn-pill turn-end">Checkmate &mdash; {winner} wins!</div>'
    if b.is_stalemate():
        return '<div class="turn-pill turn-end">Stalemate &mdash; Draw</div>'
    if b.is_insufficient_material():
        return '<div class="turn-pill turn-end">Draw &mdash; Insufficient material</div>'
    if b.is_seventyfive_moves():
        return '<div class="turn-pill turn-end">Draw &mdash; 75-move rule</div>'
    if b.is_fivefold_repetition():
        return '<div class="turn-pill turn-end">Draw &mdash; Fivefold repetition</div>'

    check = " &mdash; Check!" if b.is_check() else ""
    if b.turn == chess.WHITE:
        return f'<div class="turn-pill turn-w"><span class="dot dot-w"></span>White to move{check}</div>'
    return f'<div class="turn-pill turn-b"><span class="dot dot-b"></span>Black to move{check}</div>'


def move_list_html() -> str:
    history = st.session_state.move_history
    if not history:
        return '<div class="ml-empty">No moves yet</div>'
    total = len(history)
    rows = ""
    for i in range(0, total, 2):
        num = i // 2 + 1
        w = history[i]["san"]
        b = history[i + 1]["san"] if i + 1 < total else ""
        wc = " ml-last" if i == total - 1 else ""
        bc = " ml-last" if i + 1 == total - 1 else ""
        rows += (
            f'<div class="ml-row">'
            f'<span class="ml-num">{num}.</span>'
            f'<span class="ml-w{wc}">{w}</span>'
            f'<span class="ml-b{bc}">{b}</span>'
            f'</div>'
        )
    return f'<div class="ml-container">{rows}</div>'


def captured_html() -> tuple[str, str]:
    captured_white, captured_black = get_captured_pieces()
    adv = material_advantage()

    bk_adv = f'<span class="cap-adv">+{-adv}</span>' if adv < 0 else ""
    wh_adv = f'<span class="cap-adv">+{adv}</span>' if adv > 0 else ""

    top = f'<div class="cap-row">{"".join(captured_white)}{bk_adv}</div>'
    bot = f'<div class="cap-row">{"".join(captured_black)}{wh_adv}</div>'
    return top, bot


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CUSTOM_CSS = """
<style>
/* ---- Captured pieces ---- */
.cap-row {
    display: flex; align-items: center; gap: 1px;
    font-size: 1.05rem; min-height: 1.5rem;
    padding: 2px 0; opacity: .82;
    max-width: 600px; margin: 0 auto;
}
.cap-adv { font-size: .72rem; font-weight: 600; color: #888; margin-left: 4px; }

/* ---- Turn indicator ---- */
.turn-pill {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 6px 18px; border-radius: 999px;
    font-weight: 600; font-size: .88rem; letter-spacing: .02em;
}
.turn-w { background: #fff; color: #333; border: 2px solid #ddd; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.turn-b { background: #333; color: #fff; border: 2px solid #333; box-shadow: 0 1px 4px rgba(0,0,0,.12); }
.turn-end { background: linear-gradient(135deg, #e74c3c, #c0392b); color: #fff; border: 2px solid #c0392b; }
.dot { width: 9px; height: 9px; border-radius: 50%; display: inline-block; animation: pulse 1.6s ease-in-out infinite; }
.dot-w { background: #333; }
.dot-b { background: #fff; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.35} }

/* ---- Move list ---- */
.ml-container {
    font-family: 'SF Mono','Fira Code','Consolas', monospace;
    font-size: .8rem; max-height: 340px; overflow-y: auto;
    border: 1px solid #e2e2e2; border-radius: 8px; background: #fafafa;
    color: #333;
}
.ml-row { display: flex; padding: 4px 10px; align-items: center; }
.ml-row:nth-child(odd) { background: #f2f2f2; }
.ml-num { color: #777; min-width: 30px; font-weight: 500; }
.ml-w, .ml-b { min-width: 58px; padding: 2px 6px; border-radius: 3px; color: #222; }
.ml-last { background: #d4edda; font-weight: 600; color: #1a5928; }
.ml-empty { color: #aaa; font-style: italic; text-align: center; padding: 16px; }

/* ---- Panel headers ---- */
.ph {
    font-size: .78rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .08em; color: #888; margin-bottom: 6px;
    padding-bottom: 4px; border-bottom: 2px solid #eee;
}

/* ---- App header ---- */
.app-hdr { display: flex; align-items: baseline; gap: 10px; margin-bottom: .3rem; }
.app-hdr h1 { font-size: 1.9rem; font-weight: 700; color: #2c3e50; margin: 0; letter-spacing: -.02em; }

/* ---- Game code display ---- */
.game-code {
    font-family: 'SF Mono','Fira Code','Consolas', monospace;
    font-size: 1.8rem; font-weight: 700; letter-spacing: .15em;
    text-align: center; padding: 8px; color: #2c3e50;
}

/* ---- Misc ---- */
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }
</style>
"""


# ---------------------------------------------------------------------------
# Sidebar — game mode & multiplayer controls
# ---------------------------------------------------------------------------

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### Game Mode")
    mode = st.radio(
        "Mode", ["Local", "Multiplayer"],
        horizontal=True, label_visibility="collapsed",
        key="_mode_radio",
    )
    new_mode = mode.lower()

    # Handle mode switch
    if new_mode != st.session_state.game_mode:
        if st.session_state.game_mode == "multiplayer":
            st.session_state.game_id = None
            st.session_state.player_color = None
            st.session_state._last_db_ts = None
            st.session_state._opponent_connected = False
            st.query_params.clear()
            reset_game()
        st.session_state.game_mode = new_mode
        st.rerun()

    if st.session_state.game_mode == "multiplayer":
        st.markdown("---")

        if not st.session_state.game_id:
            # --- Create ---
            st.markdown("##### Create a game")
            create_name = st.text_input("Your name", value="Player 1", key="_create_name")
            if st.button("Create Game", use_container_width=True, type="primary"):
                gid = db.create_game(st.session_state._session_id, create_name)
                st.session_state.game_id = gid
                st.session_state.player_color = "white"
                st.session_state.white_player = create_name
                st.session_state.flip_board = False
                game = db.get_game(gid)
                st.session_state._last_db_ts = game["last_move_ts"] if game else None
                st.query_params.update(id=gid, s="white")
                st.rerun()

            st.markdown("##### Join a game")
            join_code = st.text_input("Game code", max_chars=4, key="_join_code", placeholder="ABCD")
            join_name = st.text_input("Your name", value="Player 2", key="_join_name")
            if join_code:
                if st.button("Join", use_container_width=True):
                    game = db.join_game(join_code.upper(), st.session_state._session_id, join_name)
                    if game:
                        st.session_state.game_id = join_code.upper()
                        st.session_state.player_color = "black"
                        st.session_state.black_player = join_name
                        st.session_state.white_player = game["white_player"]
                        st.session_state.flip_board = True
                        st.session_state.board = chess.Board(game["fen"])
                        st.session_state.move_history = json.loads(game["move_history"])
                        st.session_state._last_db_ts = game["last_move_ts"]
                        st.query_params.update(id=join_code.upper(), s="black")
                        st.rerun()
                    else:
                        st.error("Game not found or already full")

        else:
            # --- In a game ---
            color = st.session_state.player_color
            st.markdown(f"##### Playing as **{'White ♔' if color == 'white' else 'Black ♚'}**")
            st.markdown(
                f'<div class="game-code">{st.session_state.game_id}</div>',
                unsafe_allow_html=True,
            )

            game = db.get_game(st.session_state.game_id)
            if game:
                opp_key = "black_session" if color == "white" else "white_session"
                opp_name_key = "black_player" if color == "white" else "white_player"
                if game.get(opp_key):
                    st.success(f"vs **{game[opp_name_key]}**")
                else:
                    st.info("Waiting for opponent…")
                    st.caption("Share the code above")

            if st.button("Leave Game", use_container_width=True):
                st.session_state.game_id = None
                st.session_state.player_color = None
                st.session_state._last_db_ts = None
                st.session_state._opponent_connected = False
                st.query_params.clear()
                reset_game()
                st.rerun()


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

st.markdown(
    '<div class="app-hdr"><h1>&#9823; Chess</h1></div>',
    unsafe_allow_html=True,
)

col_board, col_panel = st.columns([3, 2], gap="large")

# Start multiplayer polling if in a game
if st.session_state.game_mode == "multiplayer" and st.session_state.game_id:
    poll_for_moves()

# ---- Board column ----
with col_board:
    st.markdown(game_status_html(), unsafe_allow_html=True)

    top_cap, bot_cap = captured_html()
    st.markdown(top_cap, unsafe_allow_html=True)

    # Interactive board component
    result = chess_board_widget(get_board_data(), key="_board_widget")

    # Process move from component (only if it's a new click)
    if result is not None:
        ts = result.get("ts")
        if ts != st.session_state.get("_last_move_ts"):
            st.session_state._last_move_ts = ts
            from_sq = result["from"]
            to_sq = result["to"]
            promo_str = result.get("promotion")
            promo_map = {"q": chess.QUEEN, "r": chess.ROOK, "b": chess.BISHOP, "n": chess.KNIGHT}
            promotion = promo_map.get(promo_str) if promo_str else None
            move = chess.Move(from_sq, to_sq, promotion=promotion)
            if move in board.legal_moves:
                make_move(move)
                st.rerun()

    st.markdown(bot_cap, unsafe_allow_html=True)

    st.write("")

    # Selectbox as alternative input (only when it's your turn)
    if not board.is_game_over() and is_my_turn():
        legal_moves = list(board.legal_moves)
        if legal_moves:
            move_sans = [board.san(m) for m in legal_moves]
            pairs = sorted(zip(move_sans, legal_moves))
            sorted_sans = [s for s, _ in pairs]
            sorted_moves = [m for _, m in pairs]

            mc = st.columns([3, 1])
            with mc[0]:
                sel = st.selectbox(
                    "Move",
                    options=sorted_sans,
                    index=None,
                    placeholder="or type a move…",
                    key="move_select",
                    label_visibility="collapsed",
                )
            with mc[1]:
                if st.button("Play ▶", use_container_width=True, type="primary"):
                    if sel:
                        move = sorted_moves[sorted_sans.index(sel)]
                        make_move(move)
                        st.rerun()

    # Controls
    is_multiplayer = st.session_state.game_mode == "multiplayer"
    bc = st.columns(3)
    with bc[0]:
        if st.button("↩ Undo", use_container_width=True,
                      disabled=not board.move_stack or is_multiplayer):
            undo_move()
            st.rerun()
    with bc[1]:
        if st.button("⟳ Flip", use_container_width=True):
            st.session_state.flip_board = not st.session_state.flip_board
            st.rerun()
    with bc[2]:
        if not is_multiplayer:
            if st.button("New Game", use_container_width=True):
                reset_game()
                st.rerun()

# ---- Side panel ----
with col_panel:
    st.markdown('<div class="ph">Players</div>', unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.session_state.white_player = st.text_input(
            "White", value=st.session_state.white_player, key="inp_white",
            disabled=is_multiplayer,
        )
    with c2:
        st.session_state.black_player = st.text_input(
            "Black", value=st.session_state.black_player, key="inp_black",
            disabled=is_multiplayer,
        )

    st.markdown('<div class="ph">Moves</div>', unsafe_allow_html=True)
    st.markdown(move_list_html(), unsafe_allow_html=True)

    with st.expander("Export Game"):
        if st.session_state.move_history:
            st.session_state.game_name = st.text_input(
                "Game name (optional)",
                value=st.session_state.game_name,
                key="inp_name",
            )
            ts_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "⬇ Download CSV",
                data=game_to_csv(),
                file_name=f"chess_{ts_str}.csv",
                mime="text/csv",
                use_container_width=True,
            )
        else:
            st.caption("Make some moves first.")

    if not is_multiplayer:
        with st.expander("Import Game"):
            uploaded = st.file_uploader(
                "Upload CSV", type=["csv"], key="csv_upload", label_visibility="collapsed",
            )
            if uploaded is not None:
                if st.button("📂 Load", use_container_width=True):
                    try:
                        load_game_from_csv(uploaded.getvalue().decode("utf-8"))
                        st.success("Game loaded!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed: {e}")

        with st.expander("FEN"):
            st.code(board.fen(), language=None)
            fen_in = st.text_input(
                "FEN", key="fen_input", label_visibility="collapsed",
                placeholder="Paste FEN here…",
            )
            if fen_in:
                if st.button("Load FEN", use_container_width=True):
                    try:
                        st.session_state.board = chess.Board(fen_in)
                        st.session_state.move_history = []
                        st.rerun()
                    except ValueError as e:
                        st.error(f"Invalid FEN: {e}")
