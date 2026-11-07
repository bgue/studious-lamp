"""Fixed names of the demo project's anchor records (P2-SEED-T05).

The drawings and model panel fixtures and plan check F4 name these records, so their numbers do
not change with the seed. ``engineering.py`` makes the two tags and ``documents.py`` the two
P&IDs. The generated records never take these numbers.
"""

from __future__ import annotations

ANCHOR_TAGS: tuple[str, ...] = ("200-V-1027", "300-T-101")
ANCHOR_DOCUMENTS: tuple[str, ...] = ("P200-200-PID-4701", "P200-200-PID-4702")
