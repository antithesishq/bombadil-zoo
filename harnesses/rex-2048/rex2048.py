#!/usr/bin/env python3
"""A sliding-tile merge game whose board is a grid of Rex panes.

`rex2048.py start` opens a Rex tab holding an N x N grid of panes and a status
pane under it. Every pane runs this script: each tile pane draws one cell, and
any pane takes the moves (arrows, wasd or hjkl), so the game works whichever
pane has focus. The panes share the board through a JSON file guarded by a
lock, and redraw when its sequence number changes.

Each tile also renames its pane to its value, and the status pane sets its
terminal title to the score and the board, so a black-box driver can read the
game from pane labels and titles as well as from the screen.

Standard library only, so it runs with macOS's /usr/bin/python3.
"""

import argparse
import fcntl
import json
import os
import random
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import termios
import time
import tty

GOAL = 2048

# ---------------------------------------------------------------- game rules


def slide_line(line):
    """Slides one line towards index 0. Returns the new line, the points
    gained, and the indices that hold a merged tile."""
    tiles = [v for v in line if v]
    out, gained, merged = [], 0, []
    i = 0
    while i < len(tiles):
        if i + 1 < len(tiles) and tiles[i] == tiles[i + 1]:
            value = tiles[i] * 2
            merged.append(len(out))
            out.append(value)
            gained += value
            i += 2
        else:
            out.append(tiles[i])
            i += 1
    return out + [0] * (len(line) - len(out)), gained, merged


def lines_for(direction, n):
    """The board's lines as lists of cell indices, each ordered from the edge
    the tiles slide towards."""
    rows = [[r * n + c for c in range(n)] for r in range(n)]
    cols = [[r * n + c for r in range(n)] for c in range(n)]
    return {
        "left": rows,
        "right": [row[::-1] for row in rows],
        "up": cols,
        "down": [col[::-1] for col in cols],
    }[direction]


def apply_move(cells, n, direction):
    """Returns (cells, gained, merged cell indices, whether anything moved)."""
    new = list(cells)
    gained, merged = 0, []
    for idxs in lines_for(direction, n):
        line, points, at = slide_line([cells[i] for i in idxs])
        for i, v in zip(idxs, line):
            new[i] = v
        gained += points
        merged += [idxs[k] for k in at]
    return new, gained, merged, new != list(cells)


def spawn(cells, rng):
    empty = [i for i, v in enumerate(cells) if not v]
    if not empty:
        return None
    i = rng.choice(empty)
    cells[i] = 4 if rng.random() < 0.1 else 2
    return i


def stuck(cells, n):
    if 0 in cells:
        return False
    for r in range(n):
        for c in range(n):
            v = cells[r * n + c]
            if c + 1 < n and cells[r * n + c + 1] == v:
                return False
            if r + 1 < n and cells[(r + 1) * n + c] == v:
                return False
    return True


def new_game(n, rng):
    cells = [0] * (n * n)
    spawned = [spawn(cells, rng), spawn(cells, rng)]
    return {
        "size": n,
        "cells": cells,
        "score": 0,
        "moves": 0,
        "won": False,
        "over": False,
        "quit": False,
        "merged": [],
        "spawned": spawned,
        "last": None,
        "seq": 0,
    }


# ------------------------------------------------------------- shared state


class Board:
    """The board file in a state directory, shared by every pane."""

    def __init__(self, state_dir):
        self.dir = state_dir
        self.path = os.path.join(state_dir, "board.json")
        self.lock_path = os.path.join(state_dir, "lock")

    def read(self):
        for _ in range(20):
            try:
                with open(self.path) as f:
                    return json.load(f)
            except (OSError, ValueError):
                time.sleep(0.01)
        return None

    def write(self, state):
        fd, tmp = tempfile.mkstemp(dir=self.dir, prefix=".board.")
        with os.fdopen(fd, "w") as f:
            json.dump(state, f)
        os.replace(tmp, self.path)

    def update(self, change):
        """Runs `change` on the board under the lock; it returns whether it
        changed anything, and only then is the board written."""
        with open(self.lock_path, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state = self.read()
            if state is not None and change(state):
                state["seq"] += 1
                self.write(state)


def do_move(board, direction):
    rng = random.Random()

    def change(state):
        if state["over"] or state["quit"]:
            return False
        n = state["size"]
        cells, gained, merged, moved = apply_move(state["cells"], n, direction)
        if not moved:
            return False
        state["spawned"] = [spawn(cells, rng)]
        state["cells"] = cells
        state["score"] += gained
        state["moves"] += 1
        state["merged"] = merged
        state["last"] = direction
        state["won"] = state["won"] or max(cells) >= GOAL
        state["over"] = stuck(cells, n)
        return True

    board.update(change)


def do_restart(board):
    def change(state):
        seq = state["seq"]
        state.clear()
        state.update(new_game(state_size(board), random.Random()))
        state["seq"] = seq
        return True

    board.update(change)


def state_size(board):
    with open(os.path.join(board.dir, "size")) as f:
        return int(f.read())


def do_quit(board):
    def change(state):
        state["quit"] = True
        return True

    board.update(change)


# ------------------------------------------------------------------ drawing

# Antithesis brand colours (24-bit), indexed by log2 of the tile: empty cells
# in plum, then greys, the coral ramp, the sky/violet ramp, and back down
# into the plums for the largest tiles. Each entry is (background, text).
ANTI_BLACK, ANTI_WHITE = "#16031B", "#FCFBF9"
PALETTE = [
    ("#310834", "#7A687B"),     # empty: Plum 800, Grey 600
    ("#E9E6E9", ANTI_BLACK),    # 2: Grey 100
    ("#D3CDD4", ANTI_BLACK),    # 4: Grey 200
    ("#FFE2DE", ANTI_BLACK),    # 8: Coral 100
    ("#FF9F91", ANTI_BLACK),    # 16: Coral 300
    ("#FF8674", ANTI_BLACK),    # 32: Coral 170C
    ("#EE6854", ANTI_WHITE),    # 64: Coral 500
    ("#B33D2B", ANTI_WHITE),    # 128: Coral 700
    ("#BB84D7", ANTI_BLACK),    # 256: Violet 2715C
    ("#8A7FFE", ANTI_WHITE),    # 512: Sky 400
    ("#685BC7", ANTI_WHITE),    # 1024: Violet 2725C
    ("#8C4799", ANTI_WHITE),    # 2048: Purple 258C
    ("#6D2077", ANTI_WHITE),    # 4096: Purple 259C
    ("#51284F", "#FF9F91"),     # 8192: Plum 262C, coral text
    (ANTI_BLACK, "#FF9F91"),    # beyond: Anti-Black, coral text
]
STATUS = ("#240627", ANTI_WHITE)    # Plum 900
STATUS_OVER = ("#B33D2B", ANTI_WHITE)  # Coral 700


def sgr(fg, bg):
    """The escape that sets 24-bit foreground and background colours."""
    rgb = lambda h: ";".join(str(int(h[i:i + 2], 16)) for i in (1, 3, 5))
    return f"\x1b[38;2;{rgb(fg)};48;2;{rgb(bg)}m"

FONT = {
    "0": ["###", "# #", "# #", "# #", "###"],
    "1": [" # ", "## ", " # ", " # ", "###"],
    "2": ["###", "  #", "###", "#  ", "###"],
    "3": ["###", "  #", " ##", "  #", "###"],
    "4": ["# #", "# #", "###", "  #", "  #"],
    "5": ["###", "#  ", "###", "  #", "###"],
    "6": ["###", "#  ", "###", "# #", "###"],
    "7": ["###", "  #", "  #", "  #", "  #"],
    "8": ["###", "# #", "###", "# #", "###"],
    "9": ["###", "# #", "###", "  #", "###"],
}


def colours(value):
    level = value.bit_length() - 1 if value else 0
    bg, fg = PALETTE[min(level, len(PALETTE) - 1)]
    return fg, bg


def big_text(text, cols, rows):
    """The text in the block font at the largest scale that fits, or None."""
    width = len(text) * 4 - 1
    for scale in (3, 2, 1):
        sx, sy = scale * 2, scale
        if width * sx <= cols - 2 and 5 * sy <= rows:
            out = []
            for glyph_row in range(5):
                line = " ".join(FONT[ch][glyph_row] for ch in text)
                wide = "".join(("█" if px == "#" else " ") * sx for px in line)
                out += [wide] * sy
            return out
    return None


def paint(lines, fg, bg, cols, rows, frame=False):
    """Fills the screen with bg and centres `lines` on it."""
    out = ["\x1b[H", sgr(fg, bg)]
    top = max(0, (rows - len(lines)) // 2)
    for r in range(rows):
        k = r - top
        text = lines[k] if 0 <= k < len(lines) else ""
        text = text[:cols]
        left = max(0, (cols - len(text)) // 2)
        row = " " * left + text
        row = row + " " * (cols - len(row))
        if frame and (r == 0 or r == rows - 1):
            row = "▀" * cols if r == 0 else "▄" * cols
        elif frame and cols >= 2:
            row = "▌" + row[1:-1] + "▐"
        out.append(f"\x1b[{r + 1};1H" + row)
    out.append("\x1b[0m")
    return "".join(out)


def draw_tile(state, index):
    cols, rows = shutil.get_terminal_size((20, 6))
    value = state["cells"][index]
    fg, bg = colours(value)
    text = str(value) if value else ""
    lines = (big_text(text, cols, rows) or [text]) if text else [""]
    merged = index in state.get("merged", [])
    if index in state.get("spawned", []):
        lines = lines + ["", "new"] if rows > len(lines) + 2 else lines
    return paint(lines, fg, bg, cols, rows, frame=merged)


ARROWS = {"left": "←", "right": "→", "up": "↑", "down": "↓", None: "·"}


def board_text(state):
    """The board as one line: rows separated by '/', empty cells as '.'."""
    n = state["size"]
    cells = state["cells"]
    return " / ".join(
        " ".join(str(v) if v else "." for v in cells[r * n:(r + 1) * n]) for r in range(n)
    )


def draw_status(state):
    cols, rows = shutil.get_terminal_size((80, 4))
    best = max(state["cells"])
    if state["over"]:
        banner = f"no moves left · score {state['score']} · r to play again"
    elif state["won"]:
        banner = f"reached {GOAL} · keep going"
    else:
        banner = f"score {state['score']} · best {best} · moves {state['moves']} · last {ARROWS[state['last']]}"
    lines = [banner, "arrows / wasd / hjkl move · r restart · q quit", "board " + board_text(state)]
    lines = lines[:rows]
    bg, fg = STATUS_OVER if state["over"] else STATUS
    return paint(lines, fg, bg, cols, rows)


# --------------------------------------------------------------- pane loop

KEYS = {
    b"\x1b[A": "up", b"\x1bOA": "up", b"w": "up", b"k": "up",
    b"\x1b[B": "down", b"\x1bOB": "down", b"s": "down", b"j": "down",
    b"\x1b[C": "right", b"\x1bOC": "right", b"d": "right", b"l": "right",
    b"\x1b[D": "left", b"\x1bOD": "left", b"a": "left", b"h": "left",
}


def parse_keys(data):
    """Splits raw input into actions."""
    out = []
    i = 0
    while i < len(data):
        for seq in (data[i:i + 3], data[i:i + 1]):
            if seq in KEYS:
                out.append(KEYS[seq])
                i += len(seq)
                break
        else:
            ch = data[i:i + 1]
            if ch in (b"r", b"R"):
                out.append("restart")
            elif ch in (b"q", b"Q", b"\x03"):
                out.append("quit")
            i += 1
    return out


def set_title(text):
    sys.stdout.write(f"\x1b]2;{text}\x07")


def rename_pane(label):
    block = os.environ.get("REX_BLOCK")
    if not block:
        return
    cmd = ["rex", "block", "rename"]
    if os.environ.get("REX_SESSION"):
        cmd += ["-s", os.environ["REX_SESSION"]]
    try:
        subprocess.Popen(cmd + [block, label], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError:
        pass


def run_pane(state_dir, index):
    """Runs a tile pane (index >= 0) or the status pane (index < 0)."""
    board = Board(state_dir)
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    tty.setraw(fd)
    sys.stdout.write("\x1b[?1049h\x1b[?25l")
    resized = [True]
    signal.signal(signal.SIGWINCH, lambda *_: resized.__setitem__(0, True))
    seen, label = None, None
    try:
        while True:
            state = board.read()
            if state is None or state["quit"]:
                return
            if state["seq"] != seen or resized[0]:
                seen, resized[0] = state["seq"], False
                if index >= 0:
                    sys.stdout.write(draw_tile(state, index))
                    value = str(state["cells"][index] or ".")
                    set_title(value)
                    if value != label:
                        label = value
                        rename_pane(f"tile {index // state['size']},{index % state['size']} = {value}")
                else:
                    sys.stdout.write(draw_status(state))
                    title = f"score {state['score']} | {board_text(state)}"
                    set_title(title)
                    if title != label:
                        label = title
                        rename_pane(title)
                sys.stdout.flush()
            try:
                ready, _, _ = select.select([fd], [], [], 0.05)
            except InterruptedError:
                continue
            if ready:
                for action in parse_keys(os.read(fd, 64)):
                    if action == "restart":
                        do_restart(board)
                    elif action == "quit":
                        do_quit(board)
                    else:
                        do_move(board, action)
    finally:
        sys.stdout.write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


# ------------------------------------------------------------------- layout


def rex(*args):
    out = subprocess.run(["rex", "--timeout=30s", *args[:args.index("--")], "--json", *args[args.index("--"):]], check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def start(args):
    n = args.size
    state_dir = args.state_dir or tempfile.mkdtemp(prefix="rex2048.")
    os.makedirs(state_dir, exist_ok=True)
    with open(os.path.join(state_dir, "size"), "w") as f:
        f.write(str(n))
    board = Board(state_dir)
    rng = random.Random(args.seed)
    state = new_game(n, rng)
    board.write(state)

    session = args.session or os.environ.get("REX_SESSION")
    me = [sys.executable, os.path.abspath(__file__)]
    pane = lambda i: ["--shell=none", "--", *me, "pane", state_dir, str(i)]

    if session:
        made = rex("window", "new", "-s", session, args.name, "--focus=false", *pane(0))
    else:
        made = rex("new", args.name, *pane(0))
        session = made["session_id"]
        made = {"window_id": made["initial_windows"][0]["window_id"],
                "block_ids": made["initial_windows"][0]["block_ids"]}
    window = made["window_id"]
    blocks = {0: made["block_ids"][0]}

    def split(anchor, direction, ratio, i):
        out = rex("split", "-s", session, "-b", anchor, f"--split={direction}",
                  f"--ratio={ratio}", "--focus=false", *pane(i))
        return out["block_ids"][0]

    split(blocks[0], "below", args.status_ratio, -1)
    for c in range(1, n):
        blocks[c] = split(blocks[c - 1], "right", round(100 * (n - c) / (n - c + 1)), c)
    for c in range(n):
        for r in range(1, n):
            blocks[r * n + c] = split(blocks[(r - 1) * n + c], "below",
                                      round(100 * (n - r) / (n - r + 1)), r * n + c)

    if args.focus:
        subprocess.run(["rex", "focus", "-s", session, window], check=False, capture_output=True)
        subprocess.run(["rex", "block", "focus", "-s", session, blocks[0]], check=False, capture_output=True)
    print(json.dumps({"session": session, "window": window, "state_dir": state_dir,
                      "blocks": [blocks[i] for i in range(n * n)]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start", help="open the game in a new Rex tab")
    s.add_argument("--size", type=int, default=4)
    s.add_argument("--session", help="Rex session (default: $REX_SESSION, else a new one)")
    s.add_argument("--name", default="2048", help="tab name")
    s.add_argument("--state-dir")
    s.add_argument("--seed", type=int)
    s.add_argument("--status-ratio", type=int, default=12)
    s.add_argument("--focus", action="store_true", help="switch to the new tab")
    p = sub.add_parser("pane", help="run one pane (started by `start`)")
    p.add_argument("state_dir")
    p.add_argument("index", type=int)
    args = parser.parse_args()
    if args.cmd == "start":
        start(args)
    else:
        run_pane(args.state_dir, args.index)


if __name__ == "__main__":
    main()
