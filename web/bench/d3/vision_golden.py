"""Writes tests/fixtures/d3-vision-golden.json: what the OFFICIAL processor and backbone of vllm-sr/d3-edge (transformers 5.17.0) give for a few pictures, so that the
TypeScript port (providers/d3Vision.ts) can be tested against it without Python: smart_resize, the patches, the position taps, the expanded prompt and the 3-row M-RoPE positions.

  python -I vision_golden.py SNAPSHOT_DIR OUT.json
The pictures are procedural, pixel(x, y, c) = (7 x + 13 y + 50 c + 31 (x * y % 5)) % 256, so the test can make the same pixels.
"""
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image


def picture(w, h):
    x = np.arange(w)[None, :, None]
    y = np.arange(h)[:, None, None]
    c = np.arange(3)[None, None, :]
    return ((7 * x + 13 * y + 50 * c + 31 * ((x * y) % 5)) % 256).astype(np.uint8)


def main(snap: str, out: str) -> None:
    sys.path.insert(0, snap)
    import d3_runtime as R
    from transformers.models.qwen2_vl.image_processing_qwen2_vl import smart_resize
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5Model  # noqa: F401  (rope index is a method of the model)
    from transformers import AutoConfig
    from transformers.vision_utils import get_vision_interpolation_indices_and_weights

    proc = R.load_processor(Path(snap))
    ip = proc.image_processor
    g = {"smart_resize": [], "pictures": [], "prompt": None}
    for h, w in [(256, 256), (384, 384), (512, 512), (300, 500), (900, 1000), (100, 100), (1500, 2000), (240, 3000), (1000, 1000), (1024, 1024)]:
        g["smart_resize"].append({"h": h, "w": w, "out": list(smart_resize(h, w, factor=32, min_pixels=65536, max_pixels=1638400))})
    for w, h in [(256, 256), (320, 256), (384, 384)]:
        arr = picture(w, h)
        img = Image.fromarray(arr, "RGB")
        enc = ip(images=[img], return_tensors="pt")
        pv = enc["pixel_values"].reshape(-1, 3, 2, 16, 16)[:, :, 0].reshape(-1, 768)
        gt, gh, gw = enc["image_grid_thw"][0].tolist()
        n = pv.shape[0]
        idx, wgt = get_vision_interpolation_indices_and_weights(enc["image_grid_thw"], 48, mode="bilinear", align_corners=True, spatial_merge_size=2)
        # raster order in HF output is merge-block order too (spatial_merge_size=2)
        sample = [0, 1, 2, 3, 4, n // 3, n // 2, n - 2, n - 1]
        g["pictures"].append({
            "w": w, "h": h, "gridH": gh, "gridW": gw, "patches": n,
            "pixelSum": float(pv.double().sum()), "pixelAbsMax": float(pv.abs().max()),
            "pixelSamples": [{"patch": i, "values": [round(float(v), 6) for v in pv[i, [0, 1, 255, 256, 511, 512, 767]]]} for i in sample],
            "idxSum": int(idx.sum()), "idxSamples": [{"patch": i, "idx": idx[i].tolist(), "w": [round(float(v), 7) for v in wgt[i]]} for i in sample],
            "wSum": float(wgt.double().sum()),
        })
    # a prompt with two pictures and the positions of the backbone
    cfg = AutoConfig.from_pretrained(snap)
    question = R.normalize_question({"type": "choice", "instructions": "Pick", "criteria": {"x": "first", "y": "second"}}).rendered
    text = proc.apply_chat_template(R.image_messages("d3", "hello", question, ["A", "B"], 2), tokenize=False, add_generation_prompt=True, enable_thinking=False)
    imgs = [Image.fromarray(picture(256, 256), "RGB"), Image.fromarray(picture(320, 256), "RGB")]
    enc = proc(text=[text], images=imgs, padding=True, return_tensors="pt")
    ids = enc["input_ids"]
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5Model as M

    class Shim:  # get_rope_index only needs config.vision_config.spatial_merge_size and get_vision_position_ids
        config = cfg
        get_vision_position_ids = M.get_vision_position_ids

    pos, _ = M.get_rope_index(Shim(), ids, enc["mm_token_type_ids"], image_grid_thw=enc["image_grid_thw"], attention_mask=enc["attention_mask"])
    g["prompt"] = {"text": text, "tokens": ids[0].tolist(), "grids": enc["image_grid_thw"].tolist(), "positions": pos[:, 0].tolist(), "imageTokenId": cfg.image_token_id}
    Path(out).write_text(json.dumps(g))
    print("wrote", out, len(json.dumps(g)) // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
