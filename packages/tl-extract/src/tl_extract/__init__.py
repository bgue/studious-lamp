"""Extractors for the derivation pipeline (brief §9 M1; ADR-0008 decision 8).

Three plugins, registered under the entry-point group ``throughline.extractors``:

* ``tabular``: CSV and XLSX, read deterministically into rows (``tl_extract.tabular``);
* ``pdf``: real PDF metadata, content stubbed (``tl_extract.pdf``);
* ``ocr``: real image-file metadata, content stubbed (``tl_extract.ocr``).

The contract is ``tl_core.derivation.types``. Nothing here touches the ledger, the network or a
file path chosen by a caller.
"""
