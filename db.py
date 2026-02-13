"""DuckDB-backed game storage for multiplayer chess."""

import duckdb
import os
import random
from datetime import datetime, timedelta

DB_PATH = os.environ.get(
    "CHESS_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "chess_games.duckdb"),
)

_CODE_CHARS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_STARTING_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


def _connect():
    return duckdb.connect(DB_PATH)


def init_db():
    """Create the games table if it doesn't exist."""
    con = _connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS games (
            game_id       VARCHAR PRIMARY KEY,
            fen           VARCHAR NOT NULL,
            move_history  VARCHAR NOT NULL DEFAULT '[]',
            white_player  VARCHAR DEFAULT 'Player 1',
            black_player  VARCHAR DEFAULT 'Player 2',
            white_session VARCHAR,
            black_session VARCHAR,
            last_move_ts  DOUBLE,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.close()


def create_game(white_session: str, white_name: str = "Player 1") -> str:
    """Create a new game and return the 4-char join code."""
    con = _connect()
    code = ""
    for _ in range(100):
        code = "".join(random.choices(_CODE_CHARS, k=4))
        if not con.execute("SELECT 1 FROM games WHERE game_id = ?", [code]).fetchone():
            break
    ts = datetime.now().timestamp()
    con.execute(
        "INSERT INTO games (game_id, fen, move_history, white_player, white_session, last_move_ts) "
        "VALUES (?, ?, '[]', ?, ?, ?)",
        [code, _STARTING_FEN, white_name, white_session, ts],
    )
    con.close()
    return code


def join_game(game_id: str, black_session: str, black_name: str = "Player 2") -> dict | None:
    """Join an existing game as black. Returns game dict or None."""
    con = _connect()
    row = con.execute("SELECT * FROM games WHERE game_id = ?", [game_id]).fetchone()
    if row is None:
        con.close()
        return None
    cols = [d[0] for d in con.description]
    game = dict(zip(cols, row))
    if game["black_session"] is not None and game["black_session"] != black_session:
        con.close()
        return None
    con.execute(
        "UPDATE games SET black_player = ?, black_session = ? WHERE game_id = ?",
        [black_name, black_session, game_id],
    )
    con.close()
    return get_game(game_id)


def get_game(game_id: str) -> dict | None:
    """Fetch the current state of a game."""
    con = _connect()
    row = con.execute("SELECT * FROM games WHERE game_id = ?", [game_id]).fetchone()
    if row is None:
        con.close()
        return None
    cols = [d[0] for d in con.description]
    con.close()
    return dict(zip(cols, row))


def update_game_move(game_id: str, fen: str, move_history_json: str) -> float:
    """Write a new board state after a move. Returns the timestamp."""
    ts = datetime.now().timestamp()
    con = _connect()
    con.execute(
        "UPDATE games SET fen = ?, move_history = ?, last_move_ts = ? WHERE game_id = ?",
        [fen, move_history_json, ts, game_id],
    )
    con.close()
    return ts


def cleanup_old_games(max_age_hours: int = 24):
    """Remove games older than *max_age_hours*."""
    con = _connect()
    cutoff = datetime.now() - timedelta(hours=max_age_hours)
    con.execute("DELETE FROM games WHERE created_at < ?", [cutoff])
    con.close()
