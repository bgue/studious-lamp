# Tests that wait for T09c

These tests were written and verified against the reference implementation of the T09c routes
(`GET /projects/{project}/tags[/{number}]`). They fail on a tree where those routes are still the
stub, so they are kept here until T09c is merged. After the merge the supervisor copies each to its
target and runs it:

| File | Target |
|---|---|
| `test_remote_tags.py.txt` | `packages/tl-tui/tests/test_remote_tags.py` |
| `test_tag_clerk_end_to_end.py.txt` | `packages/tl-sim/tests/test_tag_clerk_end_to_end.py` |
