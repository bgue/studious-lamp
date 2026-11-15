"""What the forms module makes confidential (ADR-0016, ADR-0031 decision 11).

A submission carries answers, which are record text: its class is its ``answer_class`` (copied from
the template at the first save; NULL is ``internal``). A submission with a subject is also hidden
when its subject is (``SUBJECT_LINKS`` in ``tl_core.confidentiality``), and ``OWN_CLASS_TYPES``
makes its own class count when it is higher than the subject's. A draft is read by its author alone
(a rule of ``tl_core.confidentiality``, not a class). Intake codes and items are classed through
their context only; one with no context is not hidden by this module.
"""

from __future__ import annotations

from tl_core.modules import ConfidentialSource

from tl_mod_forms.names import SUBMISSION, SUBMISSION_TABLE

CONFIDENTIAL = (
    ConfidentialSource(
        record_types=frozenset({SUBMISSION}),
        table=SUBMISSION_TABLE,
        id_column="id",
        class_column="answer_class",
        null_class="internal",
    ),
)
