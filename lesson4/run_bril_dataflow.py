
import json, os, sys
from typing import Dict, List, Tuple, Set, Any
from collections import defaultdict
sys.path.append(os.path.dirname(__file__))

from dataflow_framework import (
    Statement, BasicBlock, CFG, make_cfg,
    DataflowProblem, worklist_solve,
    reaching_definitions_problem, live_variables_problem
)

# ------------------ Bril JSON parsing ------------------

TERMINATORS = {"br", "jmp", "ret"}

def parse_bril_json(path: str) -> Dict[str, Any]:
    with open(path, "r") as f:
        return json.load(f)

def function_to_blocks(func: Dict[str, Any]) -> Tuple[Dict[str, List[str]], List[Tuple[str,str]], str, str]:
    """Convert a Bril function to blocks (id -> list of 'IR-like' text lines), edges, entry, exit."""
    instrs = func.get("instrs", [])
    # Assign implicit block ids based on labels; first block "B0" if no starting label.
    blocks: Dict[str, List[str]] = {}
    labels: Dict[str, str] = {}   # label -> block id
    order: List[str] = []

    current_block = None
    bid_counter = 0

    def start_block(name=None):
        nonlocal bid_counter, current_block
        if name is None:
            name = f"B{bid_counter}"
        bid_counter += 1
        blocks[name] = []
        order.append(name)
        current_block = name
        return name

    # Begin first block
    start_block()

    # Map labels to the *next* instruction's block
    for ins in instrs:
        if "label" in ins:
            # Start a new block at a label boundary (if current block not empty)
            if blocks[current_block]:
                start_block()
            labels[ins["label"]] = current_block
        else:
            # Convert Bril op to a string our Statement class can "use/def" from.
            # We encode "id" and "const" and all binary ops/compare/logic; calls become defs/uses too.
            s = bril_ins_to_line(ins)
            if s is not None:
                blocks[current_block].append(s)
            if ins.get("op") in TERMINATORS:
                # end this block (start a fresh one for subsequent code if any)
                start_block()

    # Now build edges based on terminators
    edges: List[Tuple[str, str]] = []
    # For convenience, build a map from block to its final terminator instr (if any)
    bterms: Dict[str, Dict] = {}
    # Re-scan to capture terminators in the same pass as above
    # We'll walk instructions again to find the terminator in each block
    # Simple approach: rebuild block->instr slices by simulating again
    cur_block_idx = 0
    cur_block = order[0]

    for ins in instrs:
        if "label" in ins:
            if blocks[order[cur_block_idx]]:  # label started new block when last ins was not a terminator
                cur_block_idx += 1
            cur_block = order[cur_block_idx]
        else:
            if ins.get("op") in TERMINATORS:
                bterms[cur_block] = ins
                cur_block_idx += 1
                if cur_block_idx < len(order):
                    cur_block = order[cur_block_idx]

    # Add fallthrough edges for non-terminated blocks to next block (if any)
    for i, b in enumerate(order):
        term = bterms.get(b)
        if term is None and i + 1 < len(order):
            edges.append((b, order[i+1]))

    # Add edges for explicit terminators
    for b, term in bterms.items():
        op = term["op"]
        if op == "jmp":
            tgt = labels[term["labels"][0]]
            edges.append((b, tgt))
        elif op == "br":
            t1, t2 = term["labels"]
            edges.append((b, labels[t1]))
            edges.append((b, labels[t2]))
        elif op == "ret":
            pass

    # Add a synthetic EXIT node
    exit_bid = "EXIT"
    blocks[exit_bid] = []
    for b, term in bterms.items():
        if term["op"] == "ret":
            edges.append((b, exit_bid))
    # if function falls off end, connect last block to EXIT
    if all(term.get("op") != "ret" for term in bterms.values()) and order:
        edges.append((order[-1], exit_bid))

    entry = order[0] if order else "EMPTY"
    return blocks, edges, entry, exit_bid

def bril_ins_to_line(ins: Dict[str, Any]) -> str:
    """Encode a Bril instruction into a pseudo-3AC string that our Statement can parse for uses/defs.
    We preserve only defs/uses; op names are ignored by the dataflow framework.
    """
    if "op" not in ins:
        return None
    op = ins["op"]
    args = ins.get("args", [])
    dest = ins.get("dest")

    if op == "const":
        if dest is None:
            return None
        return f"{dest} = const"
    if op == "id":
        if dest is None:
            return None
        return f"{dest} = {args[0]}"
    if op in {"add","sub","mul","div","eq","lt","gt","le","ge","and","or"}:
        if dest is None:
            return None
        a = args[0] if args else ""
        b = args[1] if len(args) > 1 else ""
        return f"{dest} = {a} {op} {b}"
    if op == "not":
        if dest is None:
            return None
        a = args[0] if args else ""
        return f"{dest} = {a}"
    if op == "call":
        # treat as uses of args; defines dest if present
        if dest is not None:
            rhs = " ".join(args) if args else ""
            return f"{dest} = {rhs}"
        else:
            # no dest; returns void — represent as a fake assignment to discard
            if args:
                return f"_ = {args[0]}"
            return None
    if op in {"br","jmp","ret"}:
        # control only; no defs/uses for dataflow (except br uses its cond arg)
        if op == "br" and args:
            return f"_brcond = {args[0]}"
        return None

    # Unknown op: best-effort register any args as uses and dest as def.
    if dest:
        rhs = " ".join(args) if args else ""
        return f"{dest} = {rhs}"
    return None

# ------------------ Runner ------------------

def analyze_file(path: str):
    prog = parse_bril_json(path)
    results = []
    for func in prog.get("functions", []):
        blocks, edges, entry, exit_bid = function_to_blocks(func)
        cfg = make_cfg(blocks, edges, entry, exit_bid)

        rd_prob = reaching_definitions_problem(cfg)
        rd_in, rd_out = worklist_solve(cfg, rd_prob)

        lv_prob = live_variables_problem(cfg)
        lv_in, lv_out = worklist_solve(cfg, lv_prob)

        results.append((func["name"], rd_in, rd_out, lv_in, lv_out))
    return results

def main():
    if len(sys.argv) < 2:
        print("Usage: python run_bril_dataflow.py <file_or_directory_of_json>")
        sys.exit(1)
    target = sys.argv[1]
    files = []
    if os.path.isdir(target):
        for root, _, fnames in os.walk(target):
            for fn in fnames:
                if fn.endswith(".json"):
                    files.append(os.path.join(root, fn))
    else:
        files = [target]

    for f in files:
        try:
            results = analyze_file(f)
        except Exception as e:
            print(f"[ERROR] {f}: {e}")
            continue
        print(f"# {f}")
        for (fname, rd_in, rd_out, lv_in, lv_out) in results:
            print(f"  function {fname}:")
            # Print just block keys; you can add full sets if you want verbose mode.
            print(f"    RD blocks: {sorted(rd_in.keys())}")
            print(f"    LV blocks: {sorted(lv_in.keys())}")
    print("Done.")

if __name__ == "__main__":
    main()
