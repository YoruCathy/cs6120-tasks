#!/usr/bin/env python3
import sys
import json
from collections import defaultdict, deque

TERMINATORS = {"br", "jmp", "ret"}

def label_positions(instrs):
    pos = {}
    for i, ins in enumerate(instrs):
        if "label" in ins:
            pos[ins["label"]] = i
    return pos

def leaders(instrs, lblpos):
    L = set()
    n = len(instrs)
    if n > 0:
        L.add(0)
    for i, ins in enumerate(instrs):
        op = ins.get("op")
        if op == "br":
            for tgt in ins.get("labels", []):
                if tgt in lblpos:
                    L.add(lblpos[tgt])
            if i + 1 < n:
                L.add(i + 1)
        elif op == "jmp":
            tgt = ins.get("labels", [None])[0]
            if tgt in lblpos:
                L.add(lblpos[tgt])
            if i + 1 < n:
                L.add(i + 1)
        elif "label" in ins:
            # labels are block leaders themselves
            L.add(i)
    return sorted(L)

def split_into_blocks(instrs):
    lblpos = label_positions(instrs)
    L = leaders(instrs, lblpos)
    boundaries = L + [len(instrs)]
    blocks = []
    for i in range(len(L)):
        start = boundaries[i]
        end = boundaries[i + 1]
        # skip pure-label blocks
        chunk = [ins for ins in instrs[start:end] if "label" not in ins]
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
                    # find which block contains lblpos[tgt]
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

def block_index_of_pos(leaders_list, instrs, pos):
    for i, L in enumerate(leaders_list):
        if i + 1 < len(leaders_list):
            if L <= pos < leaders_list[i + 1]:
                return i
        else:
            if L <= pos < len(instrs):
                return i
    return None


def assign_def_ids(funcs):
    did = 0
    for f in funcs:
        for ins in f.get("instrs", []):
            if "dest" in ins:
                ins["_def_id"] = did
                did += 1
    return did

def union_var_maps(maps):
    out = defaultdict(set)
    for m in maps:
        for var, defs in m.items():
            out[var] |= defs
    return dict(out)

def run_copy_aware_rd(blocks, preds):
    OUT = [dict() for _ in range(len(blocks))]
    IN = [dict() for _ in range(len(blocks))]
    work = deque(range(len(blocks)))

    while work:
        b = work.popleft()
        incoming = [OUT[p] for p in preds.get(b, [])]
        IN[b] = union_var_maps(incoming)

        cur = {v: set(s) for v, s in IN[b].items()}
        for ins in blocks[b]:
            if "op" not in ins or "dest" not in ins:
                continue
            dest = ins["dest"]
            op = ins["op"]
            if op == "id":
                # copy: inherit origin defs from source variable
                src = ins.get("args", [None])[0]
                cur[dest] = set(cur.get(src, set()))
            else:
                # non-copy: new defining site
                cur[dest] = {ins.get("_def_id")}
        if differs(OUT[b], cur):
            OUT[b] = cur
            for s in successors_of(b, preds, len(blocks)):
                work.append(s)
    return IN, OUT

def successors_of(b, preds, nblocks):
    rev = defaultdict(list)
    for v, ps in preds.items():
        for p in ps:
            rev[p].append(v)
    return rev.get(b, [])

def differs(a, b):
    if a.keys() != b.keys():
        return True
    for k in a:
        if a[k] != b[k]:
            return True
    return False


def print_result(IN, OUT):
    for i in range(len(IN)):
        print(f"Block {i}")
        print("  in:")
        for var in sorted(IN[i].keys()):
            vals = sorted(IN[i][var])
            print(f"    {var} " + " ".join(map(str, vals)))
        print("  out:")
        for var in sorted(OUT[i].keys()):
            vals = sorted(OUT[i][var])
            print(f"    {var} " + " ".join(map(str, vals)))


def main():
    program = json.load(sys.stdin)
    assign_def_ids(program.get("functions", []))

    for func in program.get("functions", []):
        instrs = func.get("instrs", [])
        blocks, edges, preds = split_into_blocks(instrs)
        IN, OUT = run_copy_aware_rd(blocks, preds)
        print(f"Function {func.get('name','<anon>')}:")
        print_result(IN, OUT)

if __name__ == "__main__":
    main()
