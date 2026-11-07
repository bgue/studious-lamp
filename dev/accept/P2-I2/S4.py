"""Acceptance for P2-I2-S4: the readiness engine. SQLite tmp db; final line ``S4 ok``."""

from __future__ import annotations

import tempfile
from pathlib import Path

import s4_steps as st
import s4_world as sw
from awp_world import hidden_record

if __name__ == "__main__":
    c2 = sw.c2_ready()
    w = sw.build(Path(tempfile.mkdtemp()) / "s4.db")
    seen = [] if c2 else sw.fake_c2(w)
    one = st.evaluation(w, c2, seen)
    st.bounds(w, one)
    st.constraint_check(w)
    st.hooks_and_jobs(w)
    st.no_text(w, one, hidden_record(w))
    print("S4 ok")
