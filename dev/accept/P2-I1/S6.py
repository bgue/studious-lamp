"""Acceptance for P2-I1-S6: the default registry expects an EWPRef link of a released CWP.
Run: ``uv run python dev/accept/P2-I1/S6.py``. One ``PASS`` per check, then ``S6 ok``."""

# ruff: noqa: E402, E501
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import S4 as s4  # the seed helpers
from tl_cli.main import app
from tl_core.links.expected import default_expected_links as default
from tl_core.links.expected import missing_expected_links as missing
from tl_core.links.expected import parse_expected_links as parse
from tl_core.services.links import AddLink, handle_add_link
from typer.testing import CliRunner


# fmt: off
def main() -> None:
    ours = default().for_type("awp.CWP")
    cwp_yaml = parse((s4.ROOT / "schema/modules/awp/cwp.yaml").read_text()).for_type("awp.CWP")
    s4.need(len(ours) == 1 and ours == cwp_yaml, f"{ours}")
    s4.passed("default registry: awp.CWP has the one expectation of cwp.yaml")
    with tempfile.TemporaryDirectory() as tmp:
        w = s4.World(Path(tmp) / "s6.db")
        for seed in (s4.people, s4.editions, s4.wbs_tree, s4.areas_and_path):
            seed(w)
        dev, rel, pwp = (s4.full_cwp(w, "PIP", f"Rack {n}", "A1", f"1.1.{n}", "10") for n in (1, 2, 3))
        def miss(cwp: str) -> int:
            with s4.open_uow(w.db, readonly=True) as uow:
                return len(missing(uow, cwp, by_state=w.state(cwp)))
        for cwp in (dev, rel, pwp):
            w.call("uma", "StartCwpDevelopment", cwp=cwp)
        s4.need(miss(dev) == 0, "In development has a miss")
        s4.passed("a CWP in development has no miss")
        for cwp in (rel, pwp):
            w.call("sue", "ReleaseCwp", cwp=cwp, expected_version=w.version(cwp))
        s4.need(miss(rel) == 1 and w.state(rel) == s4.RELEASED, "no miss, or release refused")
        s4.passed("Release succeeds; the released CWP has one MissingLink")
        for cwp, kind, number in ((rel, "ewp", "EWP-1"), (pwp, "pwp", "PWP-1")):
            w.call("uma", "RecordExternalPackage", package_type=kind, package_no=number, title=number, constraint_source=False)
            to = w.id_of(number, f"awp.{kind.upper()}Ref")
            with s4.open_uow(w.db) as uow:
                handle_add_link(uow, AddLink(actor="user:uma", source="accept", scope=s4.SCOPE, from_id=cwp, to_id=to, relation="requires"))
        s4.need(miss(rel) == 0 and miss(pwp) == 1, "EWPRef must count, PWPRef must not")
        s4.passed("a requires link to an EWPRef closes the miss; one to a PWPRef does not")
        key = w.scalar("SELECT key FROM cur_core_record WHERE id = :i", i=pwp)
        out = CliRunner().invoke(app, ["link", "list", "--project", "P123", key], env={"TL_DB": str(Path(tmp) / "s6.db"), "TL_ENV": "dev"}).output
        s4.need("missing engineering work package (rule: requires@Released" in out, out)
        s4.passed("tl link list prints the miss")
    print("S6 ok")
# fmt: on


if __name__ == "__main__":
    main()
