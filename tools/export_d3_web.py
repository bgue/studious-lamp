#!/usr/bin/env python
"""Export vllm-sr/d3-edge to ONNX for the X-ray viewer, with a vision path ("text and images").

This is OUR export. The only other browser export of d3-edge, warsang/d3-edge-web, reads text only. This tool reads the OFFICIAL checkpoint
(vllm-sr/d3-edge, Apache-2.0) and writes a folder that the viewer can load from a plain base URL (or from your own Hugging Face repository):

  MANIFEST.json  decision_config.json  tokenizer.json  tokenizer_config.json
  onnx/vision_encoder.onnx   pixel patches of one picture -> picture embeddings            (fp16 weights, fp32 inputs and outputs)
  onnx/torso_mm.onnx         input_ids + picture embeddings + M-RoPE positions -> last-position hidden state (fp16 weights)
  onnx/readout.onnx          last hidden state + option count -> 255 code logits           (fp32)

Run it in a throw-away virtual environment (it runs the repository's own modelling code, and it needs about 8 GB of memory):

  python -m venv /tmp/d3env && . /tmp/d3env/bin/activate
  pip install torch --index-url https://download.pytorch.org/whl/cpu
  pip install "transformers==5.17.0" safetensors pillow numpy onnx onnxscript onnxruntime huggingface_hub
  python tools/export_d3_web.py --checkpoint <folder or repo id> --out /tmp/d3-mm --no-optimize [--revision bee5e872f75b9c5d1405767bf244a6948b95c0af]

The three graphs, the self-check against the stock code (fp32) and MANIFEST.json come out of one run (`--only` runs one step: vision, torso, readout, fixcast, selfcheck, manifest;
`--parity-json` writes the results of an outside parity run into the manifest). Without `--no-optimize` the torso takes 20 minutes or more in the exporter's graph rewriter.

Then serve the folder over http (any static server with CORS) and put its base URL into the viewer (Classify drawer, "d3 repository": a base URL
such as http://localhost:8123/d3-mm is accepted), or upload the folder to a Hugging Face repository of your own and use its id.

What the graphs compute (all of it follows the official runtime, d3_runtime.py, "noncausal_full_attention" mode):
- torso_mm: the embedding of the prompt tokens, the rows of the <|image_pad|> tokens replaced by the picture embeddings in order (masked scatter),
  12 decoder layers (Gated DeltaNet layers keep their causal scan, the 6 full-attention layers read the whole prompt, no causal mask), the final
  RMSNorm of the LAST position only. Rotary positions are the 3 rows of the multimodal positions (T, H, W; the section split 11/11/10, interleaved).
  The sequential scan of the Gated DeltaNet is a `while_loop` over chunks of 64 tokens, so the sequence length is dynamic.
- vision_encoder: patch embedding (the Conv3d over two identical frames is folded into one matrix), learned position embedding resampled to the
  picture grid (the viewer gives the 4 gather indices and weights per patch), axial 2-D rotary, 12 blocks of full attention over the picture, merger
  (2 x 2 patches into one token). One picture per call.
- readout: the official readout.safetensors (255 x 1024, fp32) as a matrix product, the codes beyond the option count masked to -inf.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import time
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F

CHUNK = 64
OFFICIAL_REVISION = "bee5e872f75b9c5d1405767bf244a6948b95c0af"


# ------------------------------------------------------------------------------------------------ Gated DeltaNet with a while_loop

def chunk_gated_delta_rule_loop(query, key, value, g, beta, chunk_size=CHUNK, initial_state=None, output_final_state=False,
                                use_qk_l2norm_in_kernel=False, **kwargs):
    """transformers' torch_chunk_gated_delta_rule with the scan over chunks written as torch while_loop (dynamic length, exportable).

    The maths is identical: same chunk size, the same float32 intermediate values; the triangular solve is forward substitution.
    """
    from torch._higher_order_ops.while_loop import while_loop

    initial_dtype = query.dtype
    batch_size, sequence_length, _, k_head_dim = key.shape
    num_v_heads, v_head_dim = value.shape[-2:]
    decay = g
    query, key, value, beta, decay = [x.transpose(1, 2).to(torch.float32) for x in (query, key, value, beta, decay)]
    if use_qk_l2norm_in_kernel:
        query = query * torch.rsqrt((query * query).sum(dim=-1, keepdim=True) + 1e-6)
        key = key * torch.rsqrt((key * key).sum(dim=-1, keepdim=True) + 1e-6)
    query = query * (query.shape[-1] ** -0.5)
    pad_size = (chunk_size - sequence_length % chunk_size) % chunk_size
    query, key, value = (F.pad(x, (0, 0, 0, pad_size)) for x in (query, key, value))
    beta, decay = (F.pad(x, (0, pad_size)) for x in (beta, decay))
    total = sequence_length + pad_size
    num_chunks = total // chunk_size
    v_beta = value * beta.unsqueeze(-1)
    k_beta = key * beta.unsqueeze(-1)
    query, key, k_beta, v_beta = [x.reshape(x.shape[0], x.shape[1], -1, chunk_size, x.shape[-1]) for x in (query, key, k_beta, v_beta)]
    decay = decay.reshape(decay.shape[0], decay.shape[1], -1, chunk_size)
    strictly_upper = torch.ones(chunk_size, chunk_size, dtype=torch.bool).triu(1)
    cum_decay = decay.cumsum(dim=3)
    pairwise = cum_decay.unsqueeze(4) - cum_decay.unsqueeze(3)
    pairwise = pairwise.masked_fill(strictly_upper, float("-inf")).exp()
    ut_system = (k_beta @ key.transpose(-1, -2)) * pairwise
    intra = (query @ key.transpose(-1, -2)) * pairwise
    decayed_k_beta = k_beta * cum_decay.exp().unsqueeze(-1)
    # (I + A)^-1 for the strictly lower triangular A, by forward substitution as the official code does when it is exported (no triangular
    # solver in ONNX). Written without in-place updates: row i is built from the finished rows above it.
    eye = torch.eye(chunk_size, dtype=ut_system.dtype)
    low = -ut_system.tril(-1)
    done = [low[..., 0, :]]
    for i in range(1, chunk_size):
        row = low[..., i, :i]
        sub = torch.stack(done, dim=-2)[..., :i]  # finished rows 0..i-1, columns 0..i-1
        done.append(torch.cat([row + (row.unsqueeze(-1) * sub).sum(-2), low[..., i, i:]], dim=-1))
    ut = torch.stack(done, dim=-2) + eye
    new_values, k_cumdecay = ut @ v_beta, ut @ decayed_k_beta
    state = torch.zeros(batch_size, num_v_heads, k_head_dim, v_head_dim, dtype=new_values.dtype) if initial_state is None else initial_state.to(new_values)
    out = torch.zeros_like(new_values)
    query = query * cum_decay.exp().unsqueeze(-1)
    key = key * (cum_decay[..., -1:] - cum_decay).exp().unsqueeze(-1)
    chunk_decay = cum_decay[..., -1].exp()[..., None, None]

    def cond(i, state, out):
        return i < num_chunks

    def body(i, state, out):
        idx = i.reshape(1)
        nv = new_values.index_select(2, idx).squeeze(2)
        kc = k_cumdecay.index_select(2, idx).squeeze(2)
        q = query.index_select(2, idx).squeeze(2)
        ia = intra.index_select(2, idx).squeeze(2)
        k = key.index_select(2, idx).squeeze(2)
        cd = chunk_decay.index_select(2, idx).squeeze(2)
        v_new = nv - kc @ state
        chunk_out = q @ state + ia @ v_new
        new_state = state * cd + k.transpose(-1, -2) @ v_new
        new_out = out.index_copy(2, idx, chunk_out.unsqueeze(2))
        return i + 1, new_state, new_out

    i0 = torch.zeros((), dtype=torch.int64)
    _, state, out = while_loop(cond, body, (i0, state, out))
    out = out.reshape(batch_size, num_v_heads, -1, v_head_dim)[:, :, :sequence_length]
    out = out.transpose(1, 2).to(initial_dtype)
    return out, (state if output_final_state else None)


# ------------------------------------------------------------------------------------------------ the three graphs

def mrope_selector(section=(11, 11, 10), half=32) -> list[int]:
    """Which of the 3 position rows (T, H, W) drives each of the `half` rotary frequencies (interleaved M-RoPE)."""
    sel = [0] * half
    for dim, offset in ((1, 1), (2, 2)):
        for j in range(offset, section[dim] * 3, 3):
            sel[j] = dim
    return sel


class TorsoMM(nn.Module):
    """input_ids [1, L] int64, image_embeds [M, 1024] float32, position_ids [3, 1, L] int64  ->  last [1, 1024] float32."""

    def __init__(self, backbone, scan=None):
        super().__init__()
        lm = backbone.language_model
        self.cfg = lm.config
        self.embed = lm.embed_tokens
        self.layers = lm.layers
        self.norm = lm.norm
        self.image_id = backbone.config.image_token_id
        self.register_buffer("inv_freq", lm.rotary_emb.inv_freq.float().clone(), persistent=False)
        self.register_buffer("sel", torch.tensor(mrope_selector(tuple(self.cfg.rope_parameters["mrope_section"]), self.inv_freq.numel()), dtype=torch.int64), persistent=False)
        self.kinds = list(self.cfg.layer_types)
        self.dtype_ = lm.embed_tokens.weight.dtype
        self.scan = scan

    def rope(self, position_ids):
        freqs = position_ids.float().unsqueeze(-1) * self.inv_freq  # [3, 1, L, 32]
        pick = self.sel.view(1, 1, 1, -1).expand(1, freqs.shape[1], freqs.shape[2], -1)
        f = torch.gather(freqs, 0, pick)[0]  # [1, L, 32]
        emb = torch.cat([f, f], dim=-1)
        return emb.cos().to(self.dtype_), emb.sin().to(self.dtype_)

    def attention(self, a, h, cos, sin):
        b, n, _ = h.shape
        hd = a.head_dim
        q, gate = torch.chunk(a.q_proj(h).view(b, n, -1, hd * 2), 2, dim=-1)
        gate = gate.reshape(b, n, -1)
        q = a.q_norm(q.view(b, n, -1, hd)).transpose(1, 2)
        k = a.k_norm(a.k_proj(h).view(b, n, -1, hd)).transpose(1, 2)
        v = a.v_proj(h).view(b, n, -1, hd).transpose(1, 2)
        c, s = cos.unsqueeze(1), sin.unsqueeze(1)
        r = c.shape[-1]

        def rot(x):
            x1, x2 = x[..., : r // 2], x[..., r // 2: r]
            return torch.cat([x[..., :r] * c + torch.cat([-x2, x1], dim=-1) * s, x[..., r:]], dim=-1)

        q, k = rot(q), rot(k)
        rep = a.num_key_value_groups
        k = k[:, :, None].expand(b, k.shape[1], rep, n, hd).reshape(b, -1, n, hd)
        v = v[:, :, None].expand(b, v.shape[1], rep, n, hd).reshape(b, -1, n, hd)
        o = F.scaled_dot_product_attention(q, k, v, scale=a.scaling, is_causal=False)  # no mask: every position reads the whole prompt
        o = o.transpose(1, 2).reshape(b, n, -1) * torch.sigmoid(gate)
        return a.o_proj(o)

    def forward(self, input_ids, image_embeds, position_ids):
        emb = self.embed(input_ids)  # [1, L, D]
        is_image = input_ids == self.image_id  # [1, L]
        slot = (torch.cumsum(is_image.to(torch.int64), dim=1) - 1).clamp(min=0)
        picked = image_embeds.to(emb.dtype).index_select(0, slot[0]).unsqueeze(0)
        h = torch.where(is_image.unsqueeze(-1), picked, emb)
        cos, sin = self.rope(position_ids)
        for layer, kind in zip(self.layers, self.kinds):
            x = layer.input_layernorm(h)
            if kind == "linear_attention":
                x = layer.linear_attn(hidden_states=x, cache_params=None, attention_mask=None)
            else:
                x = self.attention(layer.self_attn, x, cos, sin)
            h = h + x
            h = h + layer.mlp(layer.post_attention_layernorm(h))
        return self.norm(h[:, -1:, :])[:, 0].float()


class VisionEncoder(nn.Module):
    """pixel_values [N, 768] (patches in merge-block order, channel-major, the two identical frames folded into one),
    pos_hw [N, 2] int64 (row and column of the patch), pos_idx [N, 4] int64 and pos_w [N, 4] float32 (bilinear taps into the 48 x 48 table)
    ->  embeddings [N / 4, 1024] float32."""

    def __init__(self, visual):
        super().__init__()
        self.v = visual
        pe = visual.patch_embed.proj
        w = pe.weight.detach().float().sum(dim=2)  # [768, 3, 16, 16]: both frames are the same picture
        self.patch = nn.Linear(w[0].numel(), w.shape[0], bias=True)
        self.patch.weight = nn.Parameter(w.reshape(w.shape[0], -1).to(pe.weight.dtype), requires_grad=False)
        self.patch.bias = nn.Parameter(pe.bias.detach().clone(), requires_grad=False)
        self.heads = visual.config.num_heads

    def forward(self, pixel_values, pos_hw, pos_idx, pos_w):
        v = self.v
        dt = self.patch.weight.dtype
        h = self.patch(pixel_values.to(dt))
        pe = (v.pos_embed(pos_idx) * pos_w.to(dt).unsqueeze(-1)).sum(1)
        h = h + pe
        cos, sin = v.rotary_pos_emb(h, pos_hw)  # [N, 64]
        cos, sin = cos.float().unsqueeze(1), sin.float().unsqueeze(1)
        n = h.shape[0]
        for blk in v.blocks:
            x = blk.norm1(h)
            qkv = blk.attn.qkv(x).reshape(n, 3, self.heads, -1).permute(1, 0, 2, 3)
            q, k, val = qkv[0], qkv[1], qkv[2]

            def rot(t):
                tf = t.float()
                half = tf.shape[-1] // 2
                rh = torch.cat([-tf[..., half:], tf[..., :half]], dim=-1)
                return (tf * cos + rh * sin).to(t.dtype)

            q, k = rot(q), rot(k)
            o = F.scaled_dot_product_attention(q.transpose(0, 1).unsqueeze(0), k.transpose(0, 1).unsqueeze(0), val.transpose(0, 1).unsqueeze(0),
                                               scale=blk.attn.scaling, is_causal=False)
            o = o.squeeze(0).transpose(0, 1).reshape(n, -1)
            h = h + blk.attn.proj(o)
            h = h + blk.mlp(blk.norm2(h))
        return v.merger(h).float()


class Readout(nn.Module):
    """last [1, 1024] float32, counts [1] int64 -> logits [1, 255] float32 (codes beyond counts are -inf)."""

    def __init__(self, weight):
        super().__init__()
        self.register_buffer("w", weight.float().clone(), persistent=False)

    def forward(self, last, counts):
        logits = last @ self.w.T
        idx = torch.arange(self.w.shape[0]).unsqueeze(0)
        return torch.where(idx >= counts.unsqueeze(-1), torch.full_like(logits, float("-inf")), logits)


# ------------------------------------------------------------------------------------------------ inputs of one picture (reference version of what the viewer does)

def patches_of(image, patch=16, merge=2):
    """image: float tensor [3, H, W] already scaled to (x/255 - 0.5)/0.5. -> pixel_values [N, 768], pos_hw [N, 2] (merge-block order)."""
    c, hh, ww = image.shape
    gh, gw = hh // patch, ww // patch
    x = image.reshape(c, gh // merge, merge, patch, gw // merge, merge, patch).permute(1, 4, 2, 5, 0, 3, 6)  # [bh, bw, mh, mw, c, ph, pw]
    pv = x.reshape(gh * gw, c * patch * patch)
    rows = torch.arange(gh).view(gh // merge, 1, merge, 1).expand(gh // merge, gw // merge, merge, merge)
    cols = torch.arange(gw).view(1, gw // merge, 1, merge).expand(gh // merge, gw // merge, merge, merge)
    return pv, torch.stack([rows.reshape(-1), cols.reshape(-1)], dim=-1)


def pos_taps(hw, side=48, grid=None):
    """Bilinear taps (align_corners=True) of the learned position table, per patch (same maths as transformers' vision_utils)."""
    out_i, out_w = [], []
    gh, gw = grid
    r = hw[:, 0].float()
    c = hw[:, 1].float()

    def axis(idx, size):
        src = idx * (side - 1) / max(size - 1, 1)
        fl = torch.floor(src)
        taps = torch.stack([fl, fl + 1], dim=1).long().clamp(0, side - 1)
        wts = (1 - (src.unsqueeze(1) - fl.unsqueeze(1) - torch.tensor([0.0, 1.0])).abs()).clamp(min=0)
        return taps, wts

    ht, hwt = axis(r, gh)
    wt, wwt = axis(c, gw)
    idx = (ht[:, :, None] * side + wt[:, None, :]).reshape(-1, 4)
    wgt = (hwt[:, :, None] * wwt[:, None, :]).reshape(-1, 4)
    return idx, wgt


# ------------------------------------------------------------------------------------------------ export

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def load_backbone(root: Path, dtype):
    from transformers.models.qwen3_5.modeling_qwen3_5 import Qwen3_5Model

    m = Qwen3_5Model.from_pretrained(str(root), dtype=dtype, attn_implementation="sdpa")
    return m.eval().requires_grad_(False)


def patch_scan(on: bool = True):
    """Use the while_loop version of the chunked Gated DeltaNet scan (for the export), or put the stock one back (for the self-check)."""
    from transformers.models.qwen3_5 import modeling_qwen3_5 as M

    if not hasattr(M, "_stock_chunk_rule"):
        M._stock_chunk_rule = M.torch_chunk_gated_delta_rule
    M.torch_chunk_gated_delta_rule = chunk_gated_delta_rule_loop if on else M._stock_chunk_rule


def cast_like_to_cast(path: Path) -> int:
    """Replace every CastLike node by a Cast to the element type of its `like` input (known from shape inference). onnxruntime's CPU provider (no fp16
    kernels) inserts casts around fp16 nodes and trips over CastLike with "does not match expected type (tensor(float16))" in some versions; Cast is plain."""
    import onnx
    from onnx import TensorProto, helper

    model = onnx.load(str(path))
    inferred = onnx.shape_inference.infer_shapes(model, data_prop=False)
    types = {}
    for vi in list(inferred.graph.value_info) + list(inferred.graph.input) + list(inferred.graph.output):
        if vi.type.HasField("tensor_type"):
            types[vi.name] = vi.type.tensor_type.elem_type
    for init in inferred.graph.initializer:
        types[init.name] = init.data_type
    for n in inferred.graph.node:
        if n.op_type == "Constant":
            for a in n.attribute:
                if a.name == "value":
                    types[n.output[0]] = a.t.data_type
    count = 0
    for i, node in enumerate(model.graph.node):
        if node.op_type != "CastLike":
            continue
        to = types.get(node.input[1])
        if to is None or to == TensorProto.UNDEFINED:
            raise RuntimeError(f"cannot find the type of {node.input[1]} for {node.name}")
        model.graph.node[i].CopyFrom(helper.make_node("Cast", [node.input[0]], list(node.output), name=node.name.replace("CastLike", "Cast"), to=to))
        count += 1
    onnx.save(model, str(path))
    return count


def export_graph(module, args, path: Path, input_names, output_names, dynamic_shapes, opset=20, optimize=True):
    t = time.time()
    prog = torch.onnx.export(module, args, None, input_names=input_names, output_names=output_names, dynamic_shapes=dynamic_shapes,
                             opset_version=opset, dynamo=True, optimize=optimize, do_constant_folding=True)
    prog.save(str(path), external_data=False)
    n = cast_like_to_cast(path)
    print(f"  {n} CastLike nodes became Cast", flush=True)
    print(f"  wrote {path.name}: {path.stat().st_size / 1e6:.1f} MB in {time.time() - t:.0f} s", flush=True)


def selfcheck(root: Path, out: Path) -> dict:
    """Run the exported graphs in onnxruntime and the stock transformers code (fp32, the official runtime's PromptEncoder when the checkpoint has
    d3_runtime.py) on one synthetic picture and one text prompt; report how far the last hidden states are apart."""
    import importlib.util

    import numpy as np
    import onnxruntime as ort

    spec_path = root / "d3_runtime.py"
    if not spec_path.is_file():
        return {"skipped": "the checkpoint has no d3_runtime.py"}
    sys.path.insert(0, str(root))  # d3_runtime.py imports its sibling d3_format.py
    spec = importlib.util.spec_from_file_location("d3_runtime_ref", spec_path)
    rt = importlib.util.module_from_spec(spec)
    sys.modules["d3_runtime_ref"] = rt
    spec.loader.exec_module(rt)
    patch_scan(False)
    bb = load_backbone(root, torch.float32)
    enc_ref = rt.PromptEncoder(bb.language_model)
    so = ort.SessionOptions()
    so.log_severity_level = 3
    torso = ort.InferenceSession(str(out / "onnx" / "torso_mm.onnx"), so, providers=["CPUExecutionProvider"])
    vision = ort.InferenceSession(str(out / "onnx" / "vision_encoder.onnx"), so, providers=["CPUExecutionProvider"])
    g = torch.Generator().manual_seed(7)
    image = torch.rand(3, 256, 384, generator=g) * 2 - 1
    pv, hw = patches_of(image)
    grid = (256 // 16, 384 // 16)
    idx, wgt = pos_taps(hw, grid=grid)
    emb = vision.run(None, {"pixel_values": pv.numpy(), "pos_hw": hw.numpy(), "pos_idx": idx.numpy(), "pos_w": wgt.numpy().astype(np.float32)})[0]
    with torch.inference_mode():
        # the stock vision tower on the same pixels (two identical frames, as the processor makes them)
        two = pv.reshape(-1, 3, 1, 16, 16).expand(-1, -1, 2, -1, -1).reshape(-1, 1536)
        ref_emb = torch.cat(bb.get_image_features(two, torch.tensor([[1, *grid]]), return_dict=True).pooler_output, 0).numpy()
    vis = {"max_abs": float(np.abs(emb - ref_emb).max()), "ref_max": float(np.abs(ref_emb).max()), "cosine": float((emb * ref_emb).sum() / np.linalg.norm(emb) / np.linalg.norm(ref_emb))}
    n_tok = emb.shape[0]
    pre = torch.randint(1000, 5000, (20,))
    post = torch.randint(1000, 5000, (40,))
    ids = torch.cat([pre, torch.full((n_tok,), bb.config.image_token_id), post]).unsqueeze(0)
    mm_type = (ids == bb.config.image_token_id).int()
    with torch.inference_mode():
        e0 = bb.get_input_embeddings()(ids)
        e1 = e0.masked_scatter((ids == bb.config.image_token_id).unsqueeze(-1).expand_as(e0), torch.from_numpy(ref_emb))
        mrope = bb.compute_3d_position_ids(input_ids=ids, image_grid_thw=torch.tensor([[1, *grid]]), video_grid_thw=None, inputs_embeds=e1,
                                           attention_mask=torch.ones_like(ids), past_key_values=None, mm_token_type_ids=mm_type)
        ref = enc_ref(e1, torch.ones_like(ids), mrope)[:, -1].numpy()
        text_ids = torch.randint(1000, 5000, (1, 90))
        ref_text = enc_ref(bb.get_input_embeddings()(text_ids), torch.ones_like(text_ids), None)[:, -1].numpy()
    got = torso.run(None, {"input_ids": ids.numpy(), "image_embeds": emb, "position_ids": mrope.numpy()})[0]
    got_text = torso.run(None, {"input_ids": text_ids.numpy(), "image_embeds": np.zeros((1, 1024), np.float32),
                                "position_ids": np.broadcast_to(np.arange(90)[None, None, :], (3, 1, 90)).copy()})[0]

    def cmp(a, b):
        return {"max_abs": float(np.abs(a - b).max()), "ref_max": float(np.abs(b).max()), "cosine": float((a * b).sum() / np.linalg.norm(a) / np.linalg.norm(b))}

    return {"reference": "transformers 5.17.0 fp32 with the official PromptEncoder (d3_runtime.py)", "vision": vis, "torso_picture": cmp(got, ref), "torso_text": cmp(got_text, ref_text)}


def write_manifest(root: Path, out: Path, parity: dict | None, revision: str) -> None:
    cfg = json.loads((root / "config.json").read_text())
    pre = json.loads((root / "preprocessor_config.json").read_text())
    vc = cfg["vision_config"]
    for name in ("decision_config.json", "tokenizer.json", "tokenizer_config.json", "config.json"):
        shutil.copyfile(root / name, out / name)
    graphs = {
        "torso": "onnx/torso_mm.onnx (Qwen3.5, noncausal full attention, last-position hidden; input_ids + image_embeds + 3-row M-RoPE position_ids; fp16 weights)",
        "vision": "onnx/vision_encoder.onnx (patch embedding, learned positions, axial rope, 12 blocks, merger; one picture per call; fp16 weights)",
        "readout": "onnx/readout.onnx (fp32 255 x 1024 code readout, codes beyond counts are -inf)",
    }
    names = ["config.json", "decision_config.json", "tokenizer.json", "tokenizer_config.json", "onnx/readout.onnx", "onnx/torso_mm.onnx", "onnx/vision_encoder.onnx"]
    files = {n: {"bytes": (out / n).stat().st_size, "sha256": sha256(out / n)} for n in names if (out / n).is_file()}
    manifest = {
        "model": "d3-edge-web-mm",
        "source": {"checkpoint": "vllm-sr/d3-edge", "checkpoint_revision": revision, "base_model": "Qwen/Qwen3.5-0.8B", "exporter": "tools/export_d3_web.py of the X-ray viewer"},
        "graphs": graphs,
        "scope": "text and images",
        "mm": {
            "image_token_id": cfg["image_token_id"], "vision_start_token_id": cfg["vision_start_token_id"], "vision_end_token_id": cfg["vision_end_token_id"],
            "patch_size": vc["patch_size"], "merge_size": vc["spatial_merge_size"], "temporal_patch_size": vc["temporal_patch_size"], "pos_grid": int(vc["num_position_embeddings"] ** 0.5),
            "min_pixels": 65_536, "max_pixels": 1_638_400, "image_mean": pre["image_mean"], "image_std": pre["image_std"],
            "note": "pixel_values hold one frame (the two identical frames of a still picture are folded into the patch matrix); positions are given by the viewer",
        },
        "parity": parity or {},
        "files": files,
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print("  wrote MANIFEST.json,", sum(f["bytes"] for f in files.values()) / 1e6, "MB in the files", flush=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkpoint", required=True, help="folder of vllm-sr/d3-edge, or the repository id")
    ap.add_argument("--revision", default=OFFICIAL_REVISION)
    ap.add_argument("--out", required=True)
    ap.add_argument("--only", choices=["all", "vision", "torso", "readout", "manifest", "selfcheck", "fixcast"], default="all")
    ap.add_argument("--no-optimize", action="store_true", help="skip the exporter's graph rewriter: the torso takes 1 minute instead of 20 or more, the graph is a little larger")
    ap.add_argument("--fp32", action="store_true", help="keep fp32 weights (2.4 GB torso: only for the parity check, not for the browser)")
    ap.add_argument("--parity-json", help="results of an outside parity run (bench/d3/mm_parity.mjs), written into the manifest")
    a = ap.parse_args()

    root = Path(a.checkpoint)
    if not root.is_dir():
        from huggingface_hub import snapshot_download

        root = Path(snapshot_download(a.checkpoint, revision=a.revision))
    out = Path(a.out)
    (out / "onnx").mkdir(parents=True, exist_ok=True)
    parity = json.loads(Path(a.parity_json).read_text()) if a.parity_json else {}
    if a.only == "manifest":
        write_manifest(root, out, parity, a.revision)
        return
    if a.only == "fixcast":
        for g in sorted((out / "onnx").glob("*.onnx")):
            print(g.name, cast_like_to_cast(g), "CastLike nodes became Cast")
        return
    if a.only == "selfcheck":
        print(json.dumps(selfcheck(root, out), indent=2))
        return
    dtype = torch.float32 if a.fp32 else torch.float16
    patch_scan()
    print("loading", root, flush=True)
    bb = load_backbone(root, dtype)

    if a.only in ("all", "readout"):
        from safetensors.torch import load_file

        w = load_file(str(root / "readout.safetensors"))["weight"]
        export_graph(Readout(w), (torch.zeros(1, 1024), torch.tensor([5])), out / "onnx" / "readout.onnx", ["last", "counts"], ["logits"], None)
    if a.only in ("all", "vision"):
        ve = VisionEncoder(bb.visual).eval()
        grid = (24, 24)
        img = torch.randn(3, grid[0] * 16, grid[1] * 16)
        pv, hw = patches_of(img)
        idx, wgt = pos_taps(hw, grid=grid)
        n = torch.export.Dim("patches", min=4, max=4096)
        export_graph(ve, (pv, hw, idx, wgt), out / "onnx" / "vision_encoder.onnx", ["pixel_values", "pos_hw", "pos_idx", "pos_w"], ["embeds"],
                     {"pixel_values": {0: n}, "pos_hw": {0: n}, "pos_idx": {0: n}, "pos_w": {0: n}})
    if a.only in ("all", "torso"):
        tm = TorsoMM(bb).eval()
        ids = torch.randint(0, 1000, (1, 150))
        ids[0, 10:22] = bb.config.image_token_id
        emb = torch.randn(12, 1024)
        pos = torch.arange(150).view(1, 1, -1).expand(3, 1, -1).contiguous()
        seq = torch.export.Dim("seq", min=2, max=8192)
        m = torch.export.Dim("pics", min=1, max=4096)
        export_graph(tm, (ids, emb, pos), out / "onnx" / "torso_mm.onnx", ["input_ids", "image_embeds", "position_ids"], ["last"],
                     {"input_ids": {1: seq}, "image_embeds": {0: m}, "position_ids": {2: seq}}, optimize=not a.no_optimize)
    if a.only == "all":
        del bb
        try:
            parity["selfcheck"] = selfcheck(root, out)
            print(json.dumps(parity["selfcheck"], indent=2), flush=True)
        except ImportError as e:
            parity["selfcheck"] = {"skipped": f"onnxruntime is not installed ({e})"}
        write_manifest(root, out, parity, a.revision)


if __name__ == "__main__":
    main()
