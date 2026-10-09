"""Root pytest configuration. Shared fixtures are added here by later tickets."""

import os

# Tests sign with the public dev secret: object_secret() fails closed without TL_OBJECT_SECRET or
# TL_ENV=dev (P0-I4). A test of the fail-closed behaviour passes its own mapping instead.
os.environ.setdefault("TL_ENV", "dev")
