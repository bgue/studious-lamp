"""Writes the golden prompts that tests/classify-d3-format.test.ts compares with the TypeScript port.

  python -I golden_prompts.py D3_FORMAT_PY CHAT_TEMPLATE_JINJA REQUESTS_JSON OUT_JSON
It uses d3_format.py of the official repository (revision bee5e872f75b9c5d1405767bf244a6948b95c0af) unchanged and renders the
chat template of that repository with jinja2 (what tokenizer.apply_chat_template does, enable_thinking=False). Needs jinja2 only.
"""
import importlib.util
import json
import sys

fmt_path, tpl_path, req_path, out_path = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("d3_format", fmt_path)
fmt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fmt)

from jinja2 import Environment


def raise_exception(msg):
    raise ValueError(msg)


env = Environment()
env.globals["raise_exception"] = raise_exception
template = env.from_string(open(tpl_path).read())


class Tok:
    def apply_chat_template(self, conv, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        return template.render(messages=conv, add_generation_prompt=add_generation_prompt, enable_thinking=enable_thinking, tools=None)


codes = json.load(open(req_path.replace("requests.json", "codes.json"))) if False else None
config = json.load(open(sys.argv[5])) if len(sys.argv) > 5 else None
codes = config["codes"]
out = []
for r in json.load(open(req_path)):
    for key, q in r["questions"].items():
        if q["type"] == "score":
            q = {"type": "choice", "instructions": q.get("instructions"), "criteria": {str(l): None for l in q["criteria"]}}
        out.append({"request": r["name"], "key": key, "state": r["state"], "question": r["questions"][key], "prompt": fmt.render(Tok(), r["state"], q, codes)})
json.dump(out, open(out_path, "w"), indent=1, ensure_ascii=False)
print(len(out), "prompts")
