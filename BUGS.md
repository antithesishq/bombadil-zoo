# Bugs found

Bugs found while testing with [Bombadil](https://github.com/antithesishq/bombadil), with links to upstream reports and fixes.

## Browser

## Terminal

### Upstream reports


| Target | Bug | Upstream PR |
| --- | --- | --- |
| Atuin | Copying with Ctrl+Y when search has no results panics in `swap_remove`. | [atuinsh/atuin#4426](https://github.com/atuinsh/atuin/pull/4426) |
| htop | The last read of a process's environment is counted twice, exposing uninitialised heap data as junk environment entries. | [htop-dev/htop#2136](https://github.com/htop-dev/htop/pull/2136) |
| k9s | Toggling Expand/Collapse All in Xray before its tree loads dereferences a nil root. | [derailed/k9s#4257](https://github.com/derailed/k9s/pull/4257) |
| k9s | Command-buffer notifications race with listener registration, causing a fatal concurrent map iteration/write. | [derailed/k9s#4258](https://github.com/derailed/k9s/pull/4258) |
| lazygit | Deleting the last shell-command suggestion, then deleting again, indexes the empty list at -1 and panics. | [jesseduffield/lazygit#5986](https://github.com/jesseduffield/lazygit/pull/5986) |
| Neovim | Changing an `:EditQuery` buffer's filetype makes the query linter request the wrong parser and raise autocommand errors. | [neovim/neovim#42382](https://github.com/neovim/neovim/pull/42382) |
| Neovim | Hiding the source buffer of `:InspectTree` or `:EditQuery` can make cleanup try to close the last non-floating window, raising E444. | [neovim/neovim#42383](https://github.com/neovim/neovim/pull/42383) |
| tmux | Shrinking a tiled layout loops forever when every child is already at its minimum size. | [tmux/tmux#5332](https://github.com/tmux/tmux/pull/5332) |
| tmux | Deleting a character in the prompt causes an off-by-one heap overflow. | [tmux/tmux#5478](https://github.com/tmux/tmux/pull/5478) |
| tmux | Subtracting the status border from a one-row layout cell creates a zero-height pane and pathological drawing behaviour. | [tmux/tmux#5333](https://github.com/tmux/tmux/pull/5333) |
| tmux | An invalid copy-mode search regex leaves stale search marks; resizing and scrolling can read past the old allocation. | [tmux/tmux#5547](https://github.com/tmux/tmux/pull/5547) |
| tmux | Searching lines with wide characters passes a null source to `memcpy` for zero-length cells, aborting under UBSan. | [tmux/tmux#5548](https://github.com/tmux/tmux/pull/5548) |
| tmux | Resizing a zoomed pane uses a layout cell freed by unzooming, causing a use-after-free. | [tmux/tmux#5549](https://github.com/tmux/tmux/pull/5549) |
| tview (via k9s) | Text wrapping splits multibyte characters and miscounts wide characters, producing replacement characters and premature wrapping. | [derailed/tview#13](https://github.com/derailed/tview/pull/13) |

### Fixes carried locally

These are also multiple fixes locally in the repository without an upstreamed PR. That might be because upstream isn't accepting fuzzing PR's, or PR's in general.
