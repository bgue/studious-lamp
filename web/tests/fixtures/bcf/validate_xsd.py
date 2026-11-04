#!/usr/bin/env python3
"""Validate BCF XML parts against the official buildingSMART XSDs (tests/fixtures/bcf/xsd).

Usage: python3 -I validate_xsd.py <dir> [<dir> ...]
Each <dir> holds an unpacked BCF archive. The version is read from <dir>/bcf.version (VersionId 2.1 or 3.0).
Checked: bcf.version, markup.bcf, *.bcfv, project.bcfp, extensions.xml and documents.xml (the last two for 3.0).
Prints one line per file (OK or FAIL with the first errors) and exits 1 when anything fails. Needs lxml.
"""
import os
import sys
from lxml import etree

HERE = os.path.dirname(os.path.abspath(__file__))
XSD = os.path.join(HERE, "xsd")
_cache = {}


def schema(ver, name):
    key = (ver, name)
    if key not in _cache:
        _cache[key] = etree.XMLSchema(etree.parse(os.path.join(XSD, "v21" if ver == "2.1" else "v30", name + ".xsd")))
    return _cache[key]


def kind(rel):
    base = os.path.basename(rel).lower()
    if base == "bcf.version":
        return "version"
    if base == "markup.bcf":
        return "markup"
    if base.endswith(".bcfv"):
        return "visinfo"
    if base == "project.bcfp":
        return "project"
    if base == "extensions.xml":
        return "extensions"
    if base == "documents.xml":
        return "documents"
    return None


def main(dirs):
    failed = 0
    total = 0
    for d in dirs:
        ver = etree.parse(os.path.join(d, "bcf.version")).getroot().get("VersionId")
        if ver not in ("2.1", "3.0"):
            print("FAIL %s: unsupported VersionId %r" % (d, ver))
            failed += 1
            continue
        for root, _dirs, files in os.walk(d):
            for f in sorted(files):
                rel = os.path.relpath(os.path.join(root, f), d)
                k = kind(rel)
                if not k:
                    continue
                if ver == "2.1" and k in ("extensions", "documents"):
                    continue
                total += 1
                try:
                    doc = etree.parse(os.path.join(root, f))
                    s = schema(ver, k)
                    if s.validate(doc):
                        print("OK   [%s] %s" % (ver, rel))
                    else:
                        failed += 1
                        errs = "; ".join("line %d: %s" % (e.line, e.message) for e in list(s.error_log)[:3])
                        print("FAIL [%s] %s: %s" % (ver, rel, errs))
                except Exception as e:  # noqa: BLE001
                    failed += 1
                    print("FAIL [%s] %s: %s" % (ver, rel, e))
    print("%d files, %d failed" % (total, failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
