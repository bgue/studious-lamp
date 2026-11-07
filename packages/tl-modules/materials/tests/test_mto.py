"""The MTO publish target and AssignMtoLines (S4), with the D29 pin."""

from __future__ import annotations

import acc_s4
from tl_core.derivation.registry import use_extractors
from tl_core.derivation.testing import make_extractors
from tl_core.schema_provider import DirectorySchemaProvider, use_provider
from tl_mod_documents.derivation.store import use_files


def test_publish_assign_compensate_republish(world4: acc_s4.World) -> None:
    w = world4
    with (
        use_provider(DirectorySchemaProvider(acc_s4.FIXTURES)),
        use_extractors(make_extractors()),
        use_files(w.docs.files),
    ):
        acc_s4.check_registry(w)
        acc_s4.check_mapping_refusals(w)
        fixtures = acc_s4.Fixtures(w)
        first = acc_s4.check_publish(w, fixtures)
        acc_s4.check_skip_existing(w, fixtures)
        acc_s4.check_plan_problems(w, fixtures)
        acc_s4.check_assign(w, fixtures)
        acc_s4.check_compensation_refusals(w, fixtures, first)
        acc_s4.check_compensate_and_republish(w, fixtures, first)
        acc_s4.check_word(w)
        acc_s4.check_builtin_targets(w)
