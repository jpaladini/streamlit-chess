# Streamlit Chess

A two-player chess app built with Streamlit and `python-chess`.

## Setup

```bash
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Features

- Interactive 8x8 board with click-to-select/click-to-move
- Legal move highlighting and last-move indicators
- Pawn promotion dialog
- Undo moves
- Flip board orientation
- Full move list in algebraic notation
- **Export** the game to CSV (download button)
- **Import** a previously saved CSV to resume a game
- Load/display FEN positions
- Player names and optional game name metadata
