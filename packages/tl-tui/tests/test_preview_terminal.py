"""image_protocol picks the inline-image protocol from the environment alone (P1-UX2-T01)."""

from __future__ import annotations

import pytest
from tl_tui.preview.terminal import image_protocol


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({}, "none"),
        ({"TERM": "xterm-256color"}, "none"),
        ({"TERM": "dumb", "KITTY_WINDOW_ID": "1"}, "none"),
        ({"KITTY_WINDOW_ID": "3", "TERM": "xterm-256color"}, "kitty"),
        ({"TERM": "xterm-kitty"}, "kitty"),
        ({"TERM_PROGRAM": "ghostty"}, "kitty"),
        ({"TERM_PROGRAM": "iTerm.app"}, "iterm2"),
        ({"TERM_PROGRAM": "WezTerm"}, "iterm2"),
        ({"WT_SESSION": "abc"}, "sixel"),
        ({"TERM": "foot"}, "sixel"),
        ({"TERM": "mlterm"}, "sixel"),
        ({"TERM": "xterm-sixel"}, "sixel"),
        ({"TMUX": "/tmp/tmux-0/default,1,0", "KITTY_WINDOW_ID": "3"}, "none"),
        ({"STY": "123.pts-0", "TERM_PROGRAM": "iTerm.app"}, "none"),
        ({"TL_IMAGES": "off", "KITTY_WINDOW_ID": "3"}, "none"),
        ({"TL_IMAGES": "none"}, "none"),
        ({"TL_IMAGES": "sixel"}, "sixel"),
        ({"TL_IMAGES": "kitty", "TMUX": "x"}, "kitty"),
        ({"TL_IMAGES": "bogus", "KITTY_WINDOW_ID": "3"}, "none"),
    ],
)
def test_image_protocol(env: dict[str, str], expected: str) -> None:
    assert image_protocol(env) == expected
