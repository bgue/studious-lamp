# P0-I4-T48 — HTTP client: files and the event feed

Status: ready
Tier: haiku
Labels: api
Depends on: — (the client base and the file and event routes are on the base branch)
Branch: `p0/i4c-t48-client-files-events`

## Goal
`ApiClient` can upload and download files and follow the change feed over HTTP. `packages/tl-api/src/tl_api/client/files.py` (`FilesApi`, `_check_digest`) and `events.py` (`EventsApi`, `parse_stream`) have final signatures; the bodies raise `NotImplementedError`. Implementing them is the work. Two provided test files (7 and 8 tests) must pass. This is the only ticket with streaming and reconnect logic; take the specification literally.

## Brief references (pasted)
> **20.2** Client computes SHA-256, calls register (slot, size, hash, type); the server returns a dedupe hit or an upload id; the client sends the bytes; the server verifies hash and size and attaches the file. **Quarantine:** files are unreadable by others until the scan passes.
> **5.3** Delivery is at-least-once and cursor-based (`seq`); clients resume from their last `seq`. **SSE contract (server, final):** `GET /stream?after&scope&type&record_id` sends `id: <seq>`, `event: <type>`, `data: <Event JSON>`, comment lines (`: connected`, `: keep-alive`), and honours `Last-Event-ID`.

### Specification (the provided tests check it)
**files.py** (errors are mapped by the base; never catch them)
- **`register_upload(cmd)`**: `body = cmd.model_dump(mode="json", exclude={"actor"})`; `self._model(UploadTicket, self._post_json("/uploads", body))`.
- **`upload_content(upload_id, scope, data)`**: `self._send("PUT", f"/uploads/{quote(upload_id)}/content", params={"scope": scope}, content=data, headers={"Content-Type": "application/octet-stream"})`; `self._model(FileResult, response.json())`.
- **`complete_upload(upload_id, scope)`**: `self._post_json(f"/uploads/{quote(upload_id)}/complete", None, {"scope": scope})`; `FileResult`.
- **`attach_file(cmd)`**: like `register_upload` to `/files/attach`; `FileResult`.
- **`list_files`**: `GET /records/{id}/files` with `scope`, `slot`, `current_only`; `_models(FileInfo, ...)`. **`get_file_info`**: `GET /files/{id}` with `scope`; `FileInfo`.
- **`download_file(scope, file_id)`**: `response = self._send("GET", f"/files/{quote(file_id)}/content", params={"scope": scope})`; `_check_digest(hashlib.sha256(response.content).hexdigest(), response.headers)`; return `response.content`.
- **`download_to(scope, file_id, out)`**: stream with `with self._http.stream("GET", path, params={"scope": scope}, headers=self._auth) as response:`; if `response.status_code >= 400`: `response.read()` and `raise self.error_from(response)`; otherwise write `response.iter_bytes(CHUNK)` into `out` while updating a `hashlib.sha256` and a byte count, then `_check_digest(digest.hexdigest(), response.headers)` inside the `with`; return the count.
- **`_check_digest(actual, headers)`**: `expected = headers.get("x-content-sha256")`; if it is not `None` and differs from `actual`, `raise ValueError(f"the downloaded bytes do not match the server's SHA-256 ({expected})")`.
- **`upload_file(scope, record_id, path, *, slot, content_type)`**: read `path` in `CHUNK` blocks to get its SHA-256 and size; media type = `content_type`, else `mimetypes.guess_type(path.name)[0]`, else `"application/octet-stream"`; `ticket = self.register_upload(RegisterUpload(actor=DEFAULT_ACTOR, source="client", scope=scope, record_id=record_id, slot=slot, filename=path.name, content_type=media, size=size, sha256=<hex>))`; if `ticket.exists`, return `self.complete_upload(ticket.upload_id, scope)`; else open the file in binary mode and return `self.upload_content(ticket.upload_id, scope, handle)`.

**events.py**
- **`events_after(after, *, scope, types, record_ids, limit)`**: `GET /events` with params `after`, `scope`, `type=list(types) if types else None`, `record_id=list(record_ids) if record_ids else None`, `limit`; `self._model(EventPage, data)`.
- **`parse_stream(lines)`**: collect `data:` fields (strip the 5-character prefix and one leading space) in a list; on an empty line, if there is data, yield `Event.model_validate_json("\n".join(data))` and clear it. Every other line (comments starting with `:`, `id:`, `event:`, `retry:`) is ignored.
- **`stream_events(...)`** (a generator): `last = after`, `pause = RECONNECT_FIRST_S`. Loop forever: headers = `dict(self._auth)` plus `Last-Event-ID: str(last)` when `last is not None`; params `scope`, `type`, `record_id` with `None` values left out. Inside `try:` open `with self._http.stream("GET", "/stream", params=..., headers=headers, timeout=httpx2.Timeout(10.0, read=None)) as response:`; for status >= 400 do `response.read()` and `raise self.error_from(response)`; reset `pause = RECONNECT_FIRST_S`; for each `event in parse_stream(response.iter_lines())`: skip it if `last is not None and event.seq <= last`; set `last = event.seq` and `yield event`. `except httpx2.TransportError:` re-raise when `not reconnect`. After the `try`: `if not reconnect: return`; `time.sleep(pause)`; `pause = min(pause * 2, RECONNECT_MAX_S)`; loop. Read the module attributes `RECONNECT_FIRST_S` at call time (a test patches them).
- Imports to add: `files.py`: `hashlib`, `mimetypes`, and `quote` from `tl_api.client.base`; `events.py`: `time`, `httpx2`.

Learnings that apply:
- Provided tests live under `docs/tickets/P0-I4/provided/*.py.txt`; you copy them into the test tree and must not edit the copy. The supervisor formatted them already; `diff` the copy against the original in the last acceptance step.
- The test harnesses (`packages/tl-api/tests/conftest.py`, `harness.py`; `packages/tl-mcp/tests/conftest.py`, `mcp_harness.py`) run a real app or server over a real SQLite file. Tests import them with `from harness import ...` / `from mcp_harness import ...`. Do not edit them and do not add `__init__.py` to a test directory.
- `just check` includes an OpenAPI drift check. You change no route, so it must stay green; never regenerate or edit `docs/reference/openapi.json`.
- ruff limits lines to 100 columns; run `uv run ruff format packages` before committing. `uv` prints "UV_NATIVE_TLS is deprecated"; ignore it. Do not pipe `just check` into `tail`.
- A `Blocked` caused by a red `just check` on the branch point (not by your change) is not a strike: report it and stop.
- Commit your report file (`docs/reports/P0-I4/<ticket-id>.md`); it is inside your Allowed paths.

## Interfaces (verbatim from the repo at the branch point)
```python
# packages/tl-api/src/tl_api/client/base.py (final) - the class every group below extends
class ApiClientBase:
    _http: httpx2.Client                       # one connection pool; self._auth holds the Authorization header
    def _send(self, method: str, path: str, *, params=None, json=None, content=None, headers=None) -> httpx2.Response
        # None params are dropped; status >= 400 raises the mapped exception (ServiceError subclasses, ConcurrencyError, ApiError ...)
    def _get_json(self, path: str, params: Mapping[str, Any] | None = None) -> Any
    def _post_json(self, path: str, body: Any, params: Mapping[str, Any] | None = None) -> Any
    @staticmethod def _model(model: type[M], data: Any) -> M          # model.model_validate(data)
    @staticmethod def _models(model: type[M], data: Any) -> list[M]    # a list of validated models
    def _command(self, name: str, command: Command) -> CommandResult  # POST /commands/<name>, actor left out, source kept
    @staticmethod def error_from(response: httpx2.Response) -> Exception
def quote(segment: str) -> str    # urllib.parse.quote(segment, safe=""): use it for every id put into a path
# packages/tl-api/src/tl_api/client/files.py and events.py (the stubs; keep every name and signature)
CHUNK = 1024 * 1024; DEFAULT_ACTOR = "user:client"; RECONNECT_FIRST_S = 0.25; RECONNECT_MAX_S = 5.0
class FilesApi(ApiClientBase): register_upload(cmd: RegisterUpload) -> UploadTicket; upload_content(upload_id, scope, data: bytes | BinaryIO) -> FileResult;
    complete_upload(upload_id, scope) -> FileResult; attach_file(cmd: AttachFile) -> FileResult; list_files(scope, record_id, *, slot=None, current_only=False) -> list[FileInfo];
    get_file_info(scope, file_id) -> FileInfo; download_file(scope, file_id) -> bytes; download_to(scope, file_id, out: BinaryIO) -> int;
    upload_file(scope, record_id, path: Path, *, slot=None, content_type=None) -> FileResult
def _check_digest(actual: str, headers: Mapping[str, str]) -> None
class EventsApi(ApiClientBase): events_after(after=0, *, scope=None, types=None, record_ids=None, limit=500) -> EventPage;
    stream_events(*, after=None, scope=None, types=None, record_ids=None, reconnect=True) -> Generator[Event]
def parse_stream(lines: Iterator[str]) -> Iterator[Event]
# tl_core.files.service (final): RegisterUpload / AttachFile (Command + record_id, slot, filename, content_type, size, sha256), UploadTicket(upload_id, key, exists, upload_url, expires_at), FileResult(file_id, record_id, slot, revision, sha256, size, status, deduplicated, already_attached, events)
# tl_api.models.EventPage(events: list[Event], next_seq: int, has_more: bool)
```

## Context (read these, nothing else)
- `AGENTS.md`
- `packages/tl-api/src/tl_api/client/files.py` and `events.py` (the stubs)
- `packages/tl-api/src/tl_api/client/base.py`
- `packages/tl-api/tests/harness.py`
- `docs/tickets/P0-I4/provided/test_client_files.py.txt` and `test_client_events.py.txt`
may explore: (none)

## Allowed paths
- `packages/tl-api/src/tl_api/client/files.py` and `packages/tl-api/src/tl_api/client/events.py` (edit)
- `packages/tl-api/tests/test_client_files.py` and `packages/tl-api/tests/test_client_events.py` (create: byte-for-byte copies of the provided files)
- `docs/reports/P0-I4/P0-I4-T48.md` (create: your report; commit it)

## Steps
1. `cp docs/tickets/P0-I4/provided/test_client_files.py.txt packages/tl-api/tests/test_client_files.py` and the same for `test_client_events`.
2. Implement the methods and helpers; delete the `STUB (P0-I4-T48)` paragraph from both modules.
3. Run the acceptance commands, write the report, commit both.

## Acceptance
```
uv run pytest packages/tl-api/tests/test_client_files.py packages/tl-api/tests/test_client_events.py -q
just check
just test
diff docs/tickets/P0-I4/provided/test_client_files.py.txt packages/tl-api/tests/test_client_files.py
diff docs/tickets/P0-I4/provided/test_client_events.py.txt packages/tl-api/tests/test_client_events.py
```
Expected: 15 tests pass (7 + 8), `just check` and `just test` exit 0, both `diff`s print nothing. If a streaming test hangs for more than 20 seconds, stop it, read the specification of `stream_events` again, and report *Blocked* rather than adding timeouts to the test.

## Tests to add
None beyond the provided file(s).

## Report requirements
Standard report plus the decisive lines of the acceptance commands.

## Escalation triggers
- Stop and report *Blocked* if a provided test contradicts the specification, or if you think a signature must change.
- Stop rather than change any other file.

## Blocked
(implementer writes here)

## Decision
(supervisor or orchestrator writes here)
