#!/usr/bin/env python3
import sys, json, os, argparse
from typing import Dict, List, Optional
from collections import defaultdict
from dominators import (
    CFG, compute_dominators, immediate_dominators,
    dominance_frontier, ascii_dom_tree, render_all_graphs
)

TERMINATORS = {"br", "jmp", "ret"}

def is_label(ins: Dict) -> bool:
    # Bril labels look like {"label": "L"} with no "op"
    return "label" in ins and "op" not in ins

def label_positions(instrs: List[Dict]) -> Dict[str, int]:
    pos: Dict[str, int] = {}
    for i, ins in enumerate(instrs):
        if is_label(ins):
            pos[ins["label"]] = i
    return pos

def leaders(instrs: List[Dict], lblpos: Dict[str, int]) -> List[int]:
    L = set()
    n = len(instrs)
    if n > 0:
        L.add(0)  # first instruction starts a block (prefix before first label)
    for i, ins in enumerate(instrs):
        op = ins.get("op")
        if op == "br":
            for tgt in ins.get("labels", []):
                if tgt in lblpos:
                    L.add(lblpos[tgt])
            if i + 1 < n:
                L.add(i + 1)  # fallthrough after the branch instruction
        elif op == "jmp":
            tgt = ins.get("labels", [None])[0]
            if tgt in lblpos:
                L.add(lblpos[tgt])
            if i + 1 < n:
                L.add(i + 1)
        elif is_label(ins):
            L.add(i)  # label itself starts a block
    return sorted(L)

def block_index_of_pos(leaders_list: List[int], instrs: List[Dict], pos: int) -> Optional[int]:
    for i, L in enumerate(leaders_list):
        if i + 1 < len(leaders_list):
            if L <= pos < leaders_list[i + 1]:
                return i
        else:
            if L <= pos < len(instrs):
                return i
    return None

def split_into_blocks(instrs: List[Dict]):
    """Return (blocks, edges, preds) where:
       blocks: list of lists of instructions (labels removed)
       edges:  dict int->list[int]
       preds:  dict int->list[int]
    """
    lblpos = label_positions(instrs)
    L = leaders(instrs, lblpos)
    boundaries = L + [len(instrs)]
    blocks: List[List[Dict]] = []

    # Build block contents (strip labels)
    for i in range(len(L)):
        start = boundaries[i]
        end = boundaries[i + 1]
        chunk = [ins for ins in instrs[start:end] if not is_label(ins)]
        blocks.append(chunk)

    # Build edges
    edges = defaultdict(list)
    for bidx, block in enumerate(blocks):
        if not block:
            # empty block: fallthrough to next if exists
            if bidx + 1 < len(blocks):
                edges[bidx].append(bidx + 1)
            continue
        last = block[-1]
        op = last.get("op")
        if op == "br":
            for tgt in last.get("labels", []):
                if tgt in lblpos:
                    tpos = lblpos[tgt]
                    tb = block_index_of_pos(L, instrs, tpos)
                    if tb is not None:
                        edges[bidx].append(tb)
        elif op == "jmp":
            tgt = last.get("labels", [None])[0]
            if tgt in lblpos:
                tpos = lblpos[tgt]
                tb = block_index_of_pos(L, instrs, tpos)
                if tb is not None:
                    edges[bidx].append(tb)
        elif op == "ret":
            # no fallthrough
            pass
        else:
            # fallthrough
            if bidx + 1 < len(blocks):
                edges[bidx].append(bidx + 1)

    # Predecessors
    preds = defaultdict(list)
    for u, vs in edges.items():
        for v in vs:
            preds[v].append(u)

    return blocks, edges, preds

def cfg_from_blocks(edges: Dict[int, List[int]], nb: int) -> CFG:
    """Convert block graph (0..nb-1) to our CFG (node names 'B0'..)."""
    names = [f"B{i}" for i in range(nb)]
    cfg = CFG(entry=names[0] if nb > 0 else "B0")
    for n in names:
        cfg.add_block(n)
    for u, vs in edges.items():
        for v in vs:
            cfg.add_edge(names[u], names[v])
    return cfg

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--func", help="Function name to analyze (default: first)")
    ap.add_argument("-o", "--outdir", default="bril_out", help="Output directory")
    ap.add_argument("--fmt", default="png", choices=["png", "svg", "pdf"], help="Image format")
    ap.add_argument("--view", action="store_true", help="Open rendered images")
    args = ap.parse_args()

    prog = json.load(sys.stdin)
    fns = prog.get("functions", [])
    if not fns:
        sys.exit("No functions in input")

    fn = None
    if args.func:
        for cand in fns:
            if cand.get("name") == args.func:
                fn = cand
                break
        if fn is None:
            sys.exit(f"Function {args.func} not found. Available: {[f.get('name') for f in fns]}")
    else:
        fn = fns[0]

    instrs = fn.get("instrs", [])
    blocks, edges, preds = split_into_blocks(instrs)

    # Build CFG and run analyses
    cfg = cfg_from_blocks(edges, len(blocks))
    dom = compute_dominators(cfg)
    idom = immediate_dominators(dom, cfg.entry)
    df = dominance_frontier(cfg, idom)

    print("Function:", fn.get("name", "<anon>"))
    print("Blocks:", [f"B{i}" for i in range(len(blocks))])
    print("\nASCII Dominator Tree:\n" + ascii_dom_tree(idom))

    os.makedirs(args.outdir, exist_ok=True)
    render_all_graphs(cfg, idom, df, out_dir=args.outdir, fmt=args.fmt, view=args.view)
    print(f"Wrote images to ./{args.outdir}/")

if __name__ == "__main__":
    main()
