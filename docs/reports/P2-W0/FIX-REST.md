# P2-W0-FIX-REST: end-run failures in the REST group

Worktree branch p2/w0-fix-rest (from p2/w0 at b865595). all ids fixed but one, left open as (c).
Kinds: (a) test updated to behaviour a merged ticket changed on purpose; (b) code fixed; (c) stopped.

| id | cause | kind | change |
|---|---|---|---|
| tl-cli test_cli_doc (supersede, void, confidentiality), test_cli_doc_rev (issue, supersede), test_cli_review (on_behalf), test_cli_transmittal (issue) | refusal text is now "<Cmd> needs the controller access word for documents on <scope>" (RM-S2/S3); tests looked for "admin" | a | assert "controller access word" in stderr (7 sites) |
| tl-schema test_validation: one_object_per_pset | P1-UX3 round 4: a set that allows a custom section takes ad-hoc fields, so its `x` object has `additionalProperties: true` | a | assert True for valve_data.x, with the reason |
| tl-schema test_validation: custom_section_unknown_when_pset_has_none | the test emptied `custom` but left `custom_allowed` true (P1-UX3) | a | also set `custom_allowed` False in the copied schema |
| tl-api test_error_table: every_service_error_has_its_own_row | `RoleTableError` (start-up config error, RM-S1) was unmapped; the test has no exemption list | b | row `role_table`, status 500, in `tl_api/errors.py`; openapi check passes |
| tl-mcp test_propose_import_files_a_tag_proposal... | proposing runs the command as the agent; ADR-0021: an agent with no account holds no module word | a | the fixture creates the agent account `triage` (role user -> word user) |
| tests/auth test_integration: real_account_payloads_match_catalog | `Account.ModuleRoleGranted/Revoked` joined ACCOUNT_EVENT_TYPES (RM-S1); the test never wrote them | a | the test grants and revokes a module role, so both payloads are validated |
| tests/integration test_int_runner_access (18) | fake `ControllerPing` is a controller command with no module: refused at start-up (commands.py:146, RM-S2) | a | `CommandSpec(..., module="documents")`; the guard is untouched. The fake is in no module's command index, so the runner decides it from the actor's access, which these tests probe |
| tests/services test_modules: discovery_sorted, two_modules_may_not_claim | OC-S2: a module loads only if each record type has an offline class; the fakes (`aaa.X`, `fake.Thing`) have none | a | `discover_with` sets both into `OFFLINE_CLASSES` via monkeypatch.setitem |
| tests/services test_proposal_access (4) | same agent-account cause as the MCP test (precheck runs as `agent:triage`) | a | world fixture creates the agent account |
| tl-api test_api_addable: unadopted_optional_set_is_offered... | NOT from this wave: fails the same at f950e28 (P1-UX3) in an archive of that commit. See below | c | none (file reverted) |

## Open (c): test_api_addable.py::test_an_unadopted_optional_set_is_offered_and_only_a_superuser_may_adopt_it
Three independent faults, all in the P1-UX3 design, none caused by roles/offline work:
1. Line 247 compares the unfiltered offer list with `[True]`; the fixture's other optional set `safety_data` is also offered (`[True, True]`). A test filter on NEW_SET fixes this.
2. `AdoptSchemaPackage co.acme.engineering@3.3.0` for P123 is refused ("pinned at both 3.2.0 and 3.3.0"): the fixture extension `x.P123@1.4.0` depends on 3.2.0, and the handler documents that such a pin cannot compose. Publishing an `x.P123@1.5.0` against 3.3.0 first gets past this (tried, reverted).
3. After that the pin does not make `inspection_data` effective for the project: `compose._adopted` keeps an optional set only if the project extends it, so `after.adoptable == []` and the value write cannot hold. So "adopt this set" (AdoptSchemaPackage) does not adopt a set. Whether pin should adopt, or the offer should come with an extension, is a product decision on adoption semantics (not a test edit); needs the owner.

## Gate
`just check`: lint, format, pyright, generated drift, openapi, licences all ok.
`just gate` (11 files above, test_api_addable left out): `part 1: exit 0, 383 passed in 182.91s (0:03:02)`, `gate: PASS`.
Also run: tl-api test_error_table + test_auth_roles (277 passed).
