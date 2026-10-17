"""The derivation pipeline of the documents module (brief 9 M1; ADR-0014, P1-I3).

Document schemas, derived documents and processing jobs; the job kinds that run an extractor and
validate its rows; the publication of a valid derived document into target records and its
compensation. Spec: ``docs/modules/documents/derivation.md``.
"""

from __future__ import annotations
