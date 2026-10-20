"""Tests for the codegen driver: determinism, output shape, and the --check drift gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tl_schema import generate
from tl_schema.generators import catalog

REPO_ROOT = Path(__file__).resolve().parents[3]
STATIC_KEYS = {
    "__init__.py",
    "json_schema/core.schema.json",
    "json_schema/correspondence.domain.schema.json",
    "json_schema/documents.publish-mapping.schema.json",
    "models.py",
    "ddl/postgres/auth_attempt.sql",
    "ddl/postgres/auth_audit.sql",
    "ddl/postgres/auth_credential.sql",
    "ddl/postgres/auth_session.sql",
    "ddl/postgres/auth_token_secret.sql",
    "ddl/postgres/cur_account.sql",
    "ddl/postgres/cur_action_definition.sql",
    "ddl/postgres/cur_action_invocation.sql",
    "ddl/postgres/cur_action_invocation_target.sql",
    "ddl/postgres/cur_agent_token.sql",
    "ddl/postgres/cur_core_record.sql",
    "ddl/postgres/cur_core_record_body.sql",
    "ddl/postgres/cur_core_type_registration.sql",
    "ddl/postgres/cur_correspondence_clearance.sql",
    "ddl/postgres/cur_correspondence_contact_role.sql",
    "ddl/postgres/cur_correspondence_contract_clause.sql",
    "ddl/postgres/cur_correspondence_correspondence.sql",
    "ddl/postgres/cur_correspondence_correspondence_thread.sql",
    "ddl/postgres/cur_correspondence_party.sql",
    "ddl/postgres/cur_correspondence_response_clock.sql",
    "ddl/postgres/cur_cost_cost_snapshot.sql",
    "ddl/postgres/cur_cost_costcode.sql",
    "ddl/postgres/cur_cost_snapshot_value.sql",
    "ddl/postgres/cur_documents_derived_content.sql",
    "ddl/postgres/cur_documents_derived_document.sql",
    "ddl/postgres/cur_documents_document.sql",
    "ddl/postgres/cur_documents_document_schema.sql",
    "ddl/postgres/cur_documents_processing_job.sql",
    "ddl/postgres/cur_documents_rendition.sql",
    "ddl/postgres/cur_documents_review_cycle.sql",
    "ddl/postgres/cur_documents_reviewer.sql",
    "ddl/postgres/cur_documents_revision.sql",
    "ddl/postgres/cur_documents_transmittal.sql",
    "ddl/postgres/cur_documents_transmittal_item.sql",
    "ddl/postgres/cur_engineering_code_value.sql",
    "ddl/postgres/cur_engineering_standard.sql",
    "ddl/postgres/cur_engineering_tag.sql",
    "ddl/postgres/cur_engineering_tag_class.sql",
    "ddl/postgres/cur_enricher.sql",
    "ddl/postgres/cur_enrichment_value.sql",
    "ddl/postgres/cur_feed_items.sql",
    "ddl/postgres/cur_feed_tags.sql",
    "ddl/postgres/cur_files.sql",
    "ddl/postgres/cur_inbound_endpoint.sql",
    "ddl/postgres/cur_inbound_endpoint_version.sql",
    "ddl/postgres/cur_integration_app.sql",
    "ddl/postgres/cur_link_counts.sql",
    "ddl/postgres/cur_links.sql",
    "ddl/postgres/cur_numbering.sql",
    "ddl/postgres/cur_proposals.sql",
    "ddl/postgres/cur_pset_values.sql",
    "ddl/postgres/cur_rule.sql",
    "ddl/postgres/cur_schedule_activity_ref.sql",
    "ddl/postgres/cur_schedule_schedule.sql",
    "ddl/postgres/cur_schedule_schedule_snapshot.sql",
    "ddl/postgres/cur_setting.sql",
    "ddl/postgres/cur_setting_lock.sql",
    "ddl/postgres/cur_thread.sql",
    "ddl/postgres/cur_thread_message.sql",
    "ddl/postgres/cur_thread_participant.sql",
    "ddl/postgres/cur_webhook_subscription.sql",
    "ddl/postgres/cur_workflow_state.sql",
    "ddl/postgres/enrich_cursor.sql",
    "ddl/postgres/int_counter.sql",
    "ddl/postgres/int_delivery.sql",
    "ddl/postgres/int_replay.sql",
    "ddl/postgres/int_secret.sql",
    "ddl/postgres/job_queue.sql",
    "ddl/postgres/outbox_events.sql",
    "ddl/postgres/rule_cursor.sql",
    "ddl/postgres/rule_firing.sql",
    "ddl/postgres/sched_activity.sql",
    "ddl/postgres/sched_activity_code.sql",
    "ddl/postgres/sched_calendar.sql",
    "ddl/postgres/sched_relationship.sql",
    "ddl/postgres/sched_udf_value.sql",
    "ddl/postgres/sched_wbs.sql",
    "ddl/postgres/setting_effect_applied.sql",
    "ddl/postgres/tl_body_quarantine.sql",
    "ddl/postgres/v_correspondence_contract_clause.sql",
    "ddl/postgres/v_correspondence_correspondence.sql",
    "ddl/postgres/v_correspondence_correspondence_thread.sql",
    "ddl/postgres/v_correspondence_party.sql",
    "ddl/postgres/v_correspondence_response_clock.sql",
    "ddl/postgres/v_cost_cost_code.sql",
    "ddl/postgres/v_cost_cost_snapshot.sql",
    "ddl/postgres/v_documents_derived_document.sql",
    "ddl/postgres/v_documents_document.sql",
    "ddl/postgres/v_documents_document_schema.sql",
    "ddl/postgres/v_documents_processing_job.sql",
    "ddl/postgres/v_documents_rendition.sql",
    "ddl/postgres/v_documents_review_cycle.sql",
    "ddl/postgres/v_documents_revision.sql",
    "ddl/postgres/v_documents_transmittal.sql",
    "ddl/postgres/v_engineering_code_value.sql",
    "ddl/postgres/v_engineering_standard.sql",
    "ddl/postgres/v_engineering_tag.sql",
    "ddl/postgres/v_engineering_tag_class.sql",
    "ddl/postgres/v_schedule_activity_ref.sql",
    "ddl/postgres/v_schedule_schedule.sql",
    "ddl/postgres/v_schedule_schedule_snapshot.sql",
    "ddl/postgres/wh_attempt.sql",
    "ddl/postgres/wh_cursor.sql",
    "ddl/postgres/wh_delivery.sql",
    "ddl/postgres/wh_health.sql",
    "ddl/postgres/wh_secret.sql",
    "ddl/sqlite/auth_attempt.sql",
    "ddl/sqlite/auth_audit.sql",
    "ddl/sqlite/auth_credential.sql",
    "ddl/sqlite/auth_session.sql",
    "ddl/sqlite/auth_token_secret.sql",
    "ddl/sqlite/cur_account.sql",
    "ddl/sqlite/cur_action_definition.sql",
    "ddl/sqlite/cur_action_invocation.sql",
    "ddl/sqlite/cur_action_invocation_target.sql",
    "ddl/sqlite/cur_agent_token.sql",
    "ddl/sqlite/cur_core_record.sql",
    "ddl/sqlite/cur_core_record_body.sql",
    "ddl/sqlite/cur_core_type_registration.sql",
    "ddl/sqlite/cur_correspondence_clearance.sql",
    "ddl/sqlite/cur_correspondence_contact_role.sql",
    "ddl/sqlite/cur_correspondence_contract_clause.sql",
    "ddl/sqlite/cur_correspondence_correspondence.sql",
    "ddl/sqlite/cur_correspondence_correspondence_thread.sql",
    "ddl/sqlite/cur_correspondence_party.sql",
    "ddl/sqlite/cur_correspondence_response_clock.sql",
    "ddl/sqlite/cur_cost_cost_snapshot.sql",
    "ddl/sqlite/cur_cost_costcode.sql",
    "ddl/sqlite/cur_cost_snapshot_value.sql",
    "ddl/sqlite/cur_documents_derived_content.sql",
    "ddl/sqlite/cur_documents_derived_document.sql",
    "ddl/sqlite/cur_documents_document.sql",
    "ddl/sqlite/cur_documents_document_schema.sql",
    "ddl/sqlite/cur_documents_processing_job.sql",
    "ddl/sqlite/cur_documents_rendition.sql",
    "ddl/sqlite/cur_documents_review_cycle.sql",
    "ddl/sqlite/cur_documents_reviewer.sql",
    "ddl/sqlite/cur_documents_revision.sql",
    "ddl/sqlite/cur_documents_transmittal.sql",
    "ddl/sqlite/cur_documents_transmittal_item.sql",
    "ddl/sqlite/cur_engineering_code_value.sql",
    "ddl/sqlite/cur_engineering_standard.sql",
    "ddl/sqlite/cur_engineering_tag.sql",
    "ddl/sqlite/cur_engineering_tag_class.sql",
    "ddl/sqlite/cur_enricher.sql",
    "ddl/sqlite/cur_enrichment_value.sql",
    "ddl/sqlite/cur_feed_items.sql",
    "ddl/sqlite/cur_feed_tags.sql",
    "ddl/sqlite/cur_files.sql",
    "ddl/sqlite/cur_inbound_endpoint.sql",
    "ddl/sqlite/cur_inbound_endpoint_version.sql",
    "ddl/sqlite/cur_integration_app.sql",
    "ddl/sqlite/cur_link_counts.sql",
    "ddl/sqlite/cur_links.sql",
    "ddl/sqlite/cur_numbering.sql",
    "ddl/sqlite/cur_proposals.sql",
    "ddl/sqlite/cur_pset_values.sql",
    "ddl/sqlite/cur_rule.sql",
    "ddl/sqlite/cur_schedule_activity_ref.sql",
    "ddl/sqlite/cur_schedule_schedule.sql",
    "ddl/sqlite/cur_schedule_schedule_snapshot.sql",
    "ddl/sqlite/cur_setting.sql",
    "ddl/sqlite/cur_setting_lock.sql",
    "ddl/sqlite/cur_thread.sql",
    "ddl/sqlite/cur_thread_message.sql",
    "ddl/sqlite/cur_thread_participant.sql",
    "ddl/sqlite/cur_webhook_subscription.sql",
    "ddl/sqlite/cur_workflow_state.sql",
    "ddl/sqlite/enrich_cursor.sql",
    "ddl/sqlite/int_counter.sql",
    "ddl/sqlite/int_delivery.sql",
    "ddl/sqlite/int_replay.sql",
    "ddl/sqlite/int_secret.sql",
    "ddl/sqlite/job_queue.sql",
    "ddl/sqlite/outbox_events.sql",
    "ddl/sqlite/rule_cursor.sql",
    "ddl/sqlite/rule_firing.sql",
    "ddl/sqlite/sched_activity.sql",
    "ddl/sqlite/sched_activity_code.sql",
    "ddl/sqlite/sched_calendar.sql",
    "ddl/sqlite/sched_relationship.sql",
    "ddl/sqlite/sched_udf_value.sql",
    "ddl/sqlite/sched_wbs.sql",
    "ddl/sqlite/setting_effect_applied.sql",
    "ddl/sqlite/tl_body_quarantine.sql",
    "ddl/sqlite/v_correspondence_contract_clause.sql",
    "ddl/sqlite/v_correspondence_correspondence.sql",
    "ddl/sqlite/v_correspondence_correspondence_thread.sql",
    "ddl/sqlite/v_correspondence_party.sql",
    "ddl/sqlite/v_correspondence_response_clock.sql",
    "ddl/sqlite/v_cost_cost_code.sql",
    "ddl/sqlite/v_cost_cost_snapshot.sql",
    "ddl/sqlite/v_documents_derived_document.sql",
    "ddl/sqlite/v_documents_document.sql",
    "ddl/sqlite/v_documents_document_schema.sql",
    "ddl/sqlite/v_documents_processing_job.sql",
    "ddl/sqlite/v_documents_rendition.sql",
    "ddl/sqlite/v_documents_review_cycle.sql",
    "ddl/sqlite/v_documents_revision.sql",
    "ddl/sqlite/v_documents_transmittal.sql",
    "ddl/sqlite/v_engineering_code_value.sql",
    "ddl/sqlite/v_engineering_standard.sql",
    "ddl/sqlite/v_engineering_tag.sql",
    "ddl/sqlite/v_engineering_tag_class.sql",
    "ddl/sqlite/v_schedule_activity_ref.sql",
    "ddl/sqlite/v_schedule_schedule.sql",
    "ddl/sqlite/v_schedule_schedule_snapshot.sql",
    "ddl/sqlite/wh_attempt.sql",
    "ddl/sqlite/wh_cursor.sql",
    "ddl/sqlite/wh_delivery.sql",
    "ddl/sqlite/wh_health.sql",
    "ddl/sqlite/wh_secret.sql",
}


def _catalog_keys() -> set[str]:
    keys = {"catalog/index.json", "catalog/asyncapi.json", "docs/event-catalog.md"}
    for event in catalog.build_events(generate.SCHEMA_DIR):
        stem = catalog.file_stem(event.event_type, event.version)
        keys |= {f"catalog/schemas/{stem}.json", f"catalog/samples/{stem}.json"}
    return keys


EXPECTED_KEYS = STATIC_KEYS | _catalog_keys()


def test_outputs_has_expected_keys_and_is_deterministic() -> None:
    first = generate.outputs()
    second = generate.outputs()
    assert set(first) == EXPECTED_KEYS
    assert list(first) == sorted(first)
    assert first == second


def test_outputs_contain_no_machine_paths() -> None:
    files = generate.outputs()
    for path, text in files.items():
        assert str(generate.SCHEMA_DIR) not in text, path
        assert str(generate.GENERATED_DIR) not in text, path
        assert str(REPO_ROOT) not in text, path
        assert text.endswith("\n") and not text.endswith("\n\n"), path


def test_models_define_record_and_event() -> None:
    models = generate.outputs()["models.py"]
    assert "class Record(" in models
    assert "class Event(" in models


def test_json_schema_defines_record_and_event() -> None:
    schema = json.loads(generate.outputs()["json_schema/core.schema.json"])
    assert "Record" in schema["$defs"]
    assert "Event" in schema["$defs"]


def test_main_writes_then_checks_clean(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert generate.main(["--out", str(tmp_path)]) == 0
    assert generate.existing(tmp_path) == EXPECTED_KEYS
    assert generate.main(["--check", "--out", str(tmp_path)]) == 0
    assert f"generated files are up to date ({len(EXPECTED_KEYS)} files)" in capsys.readouterr().out


def test_check_reports_differs_missing_stale_and_repair(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert generate.main(["--out", str(tmp_path)]) == 0
    capsys.readouterr()

    # Edit a file: the check must name it as differing.
    models = tmp_path / "models.py"
    models.write_text(models.read_text(encoding="utf-8") + "# x\n", encoding="utf-8")
    assert generate.main(["--check", "--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "differs: models.py" in err
    assert "codegen drift: run `just gen` and commit the result" in err

    # Delete a file: the check must name it as missing.
    (tmp_path / "json_schema" / "core.schema.json").unlink()
    assert generate.main(["--check", "--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "missing: json_schema/core.schema.json" in err

    # Add a file the generators do not produce: the check must name it as stale.
    (tmp_path / "extra.py").write_text("# extra\n", encoding="utf-8")
    assert generate.main(["--check", "--out", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert "stale: extra.py" in err

    # Re-running the writer repairs all three problems.
    assert generate.main(["--out", str(tmp_path)]) == 0
    capsys.readouterr()
    assert generate.main(["--check", "--out", str(tmp_path)]) == 0
    assert "generated files are up to date" in capsys.readouterr().out


def test_ignores_pycache_directory(tmp_path: Path) -> None:
    assert generate.main(["--out", str(tmp_path)]) == 0
    cache = tmp_path / "__pycache__"
    cache.mkdir()
    (cache / "models.cpython-312.pyc").write_bytes(b"\x00")
    assert generate.existing(tmp_path) == EXPECTED_KEYS
    assert generate.main(["--check", "--out", str(tmp_path)]) == 0


def test_committed_generated_directory_is_in_sync() -> None:
    assert generate.main(["--check"]) == 0
