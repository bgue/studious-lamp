"""Reference run of the OFFICIAL vllm-sr/d3-edge (PyTorch, CPU) for the parity check with the TypeScript port.

  python -I reference.py REQUESTS.json OUT.json
Needs: pip install torch (CPU) "transformers==5.17.0" safetensors pillow huggingface_hub jinja2 numpy tokenizers
It loads the model with trust_remote_code=True at the pinned revision, so it runs the repository's own Python code: run it in a
throw-away virtual environment, never in the project. Writes the prompt text, the token ids and the answers of every request.
"""
import json
import sys
import time

REVISION = "bee5e872f75b9c5d1405767bf244a6948b95c0af"


def main(req_path: str, out_path: str) -> None:
    from transformers import AutoModel

    requests = json.load(open(req_path))
    t0 = time.time()
    model = AutoModel.from_pretrained("vllm-sr/d3-edge", trust_remote_code=True, revision=REVISION, device="cpu")
    print("loaded in", round(time.time() - t0, 1), "s", flush=True)
    rt = model.runtime
    mod = sys.modules[type(rt).__module__]
    out = []
    for r in requests:
        t1 = time.time()
        res = model.system_one(state=r["state"], questions=r["questions"])
        ms = round((time.time() - t1) * 1000)
        prompts, ids = {}, {}
        for k, q in r["questions"].items():
            text = rt.text(r["state"], mod.normalize_question(q).rendered)
            prompts[k] = text
            ids[k] = rt.tokenizer(text, add_special_tokens=False)["input_ids"]
        out.append({"name": r["name"], "ms": ms, "prompts": prompts, "ids": ids, "answers": res["answers"], "usage": res["usage"]})
        print(r["name"], ms, "ms", flush=True)
    json.dump(out, open(out_path, "w"), indent=2)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
