# rex-2048

A sliding-tile merge game whose board is a grid of Rex panes, as a target for
Bombadil's macOS driver driving Rex.app, guided by Quest.

```sh
python3 harnesses/rex-2048/rex2048.py start --focus     # 4x4 in $REX_SESSION
python3 harnesses/rex-2048/rex2048.py start --size 3 --seed 1
```

Every pane takes moves (arrows, wasd, hjkl), `r` restarts and `q` quits, so the
driver can press arrow keys in Rex.app whichever pane has focus. The panes
share the board through `board.json` in a state directory.

The state is readable without instrumentation, as an abstraction over pane
labels (like a cube's sticker colours):

- each tile renames its pane to `tile r,c = <value>` (`.` when empty) and sets
  its terminal title to the value;
- the status pane's label and title are `score N | <row> / <row> / ...`.

Tiles use the Antithesis brand palette (24-bit colour). Standard library only,
so it runs with macOS's `/usr/bin/python3`.
