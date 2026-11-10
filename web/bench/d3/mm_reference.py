"""Reference run of the OFFICIAL vllm-sr/d3-edge (PyTorch, CPU, bf16) with pictures, for the parity check with the ONNX export and its TypeScript port.

  python -I mm_reference.py REQUESTS.json OUT.json [SNAPSHOT_DIR]
REQUESTS.json comes from make-mm-requests.mjs: a list of {name, state, questions, images: [paths]}. The model runs `system_one(state=..., questions=..., images=paths)` with
trust_remote_code, so run it in a throw-away virtual environment (see tools/export_d3_web.py). Writes the answers, the prompt text (placeholders expanded),
the number of tokens and the time of every request. For an image that has no `rgba` entry (a PNG such as the model card's receipt) it also writes the RGB pixels
as RGBA next to the file (<file>.rgba) and adds them to the request, so that mm_parity.mjs can read them without a PNG decoder.
"""
import json
import sys
import time
from pathlib import Path

REVISION = "bee5e872f75b9c5d1405767bf244a6948b95c0af"


def main(req_path: str, out_path: str, snapshot: str | None) -> None:
    from PIL import Image
    from transformers import AutoModel

    requests = json.load(open(req_path))
    t0 = time.time()
    model = AutoModel.from_pretrained(snapshot or "vllm-sr/d3-edge", trust_remote_code=True, revision=None if snapshot else REVISION, device="cpu", local_files_only=bool(snapshot))
    print("loaded in", round(time.time() - t0, 1), "s", flush=True)
    rt = model.runtime
    mod = sys.modules[type(rt).__module__]
    out = []
    for r in requests:
        images = r.get("images") or []
        if images and not r.get("rgba"):
            r["rgba"] = []
            for p in images:
                im = Image.open(p).convert("RGB")
                rgba = Path(str(p) + ".rgba")
                rgba.write_bytes(im.convert("RGBA").tobytes())
                r["rgba"].append({"file": str(rgba), "width": im.width, "height": im.height})
        t1 = time.time()
        res = model.system_one(state=r["state"], questions=r["questions"], images=images or None)
        ms = round((time.time() - t1) * 1000)
        prompts = {}
        for k, q in r["questions"].items():
            n = mod.normalize_question(q).rendered
            prompts[k] = rt.image_text(r["state"], n, len(images)) if images else rt.text(r["state"], n)
        out.append({"name": r["name"], "ms": ms, "prompts": prompts, "answers": res["answers"], "usage": res["usage"]})
        print(r["name"], ms, "ms", res["usage"], flush=True)
    json.dump(out, open(out_path, "w"), indent=2)
    json.dump(requests, open(req_path, "w"), indent=2)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
