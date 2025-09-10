#!/usr/bin/env python3
import json
import sys
from typing import List, Dict, Tuple, Any

TERMINATORS = {"jmp", "br", "ret"}


def is_label(instr: Dict[str, Any]) -> bool:
    return "label" in instr


def is_terminator(instr: Dict[str, Any]) -> bool:
    op = instr.get("op")
    return op in TERMINATORS


def target_labels(instr: Dict[str, Any]) -> List[str]:
    """
    Return the list of label targets for control-transfer instructions.
    - jmp: ["L"]
    - br:  ["L_true", "L_false"]  (order preserved)
    - ret / others: []
    """
    if instr.get("op") == "jmp":
        return instr.get("labels", [])
    if instr.get("op") == "br":
        return instr.get("labels", [])
    return []


def find_leaders(instrs: List[Dict[str, Any]]) -> List[int]:
    """
    Return instruction indices that start a basic block (leaders).
    Leaders:
      1) first instruction
      2) any instruction that is the target of a jump/branch (i.e., labels)
      3) instruction immediately following a terminator (fall-through split)
    """
    leaders = set()
    if instrs:
        leaders.add(0)

    # Collect label positions
    label_pos: Dict[str, int] = {}
    for i, ins in enumerate(instrs):
        if is_label(ins):
            label_pos[ins["label"]] = i

    # Any label target is a leader
    for ins in instrs:
        for L in target_labels(ins):
            if L in label_pos:
                leaders.add(label_pos[L])

    # Instruction after a terminator is a leader (if exists)
    for i, ins in enumerate(instrs):
        if is_terminator(ins) and i + 1 < len(instrs):
            leaders.add(i + 1)

    return sorted(leaders)


def make_blocks(instrs: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """
    Partition instructions into basic blocks.
    Returns:
      blocks: list of dicts { "name": str, "start": int, "end": int, "instrs": [...] }
      label2block: mapping from label name to block index (block that starts at that label)
    Block naming:
      - If a block starts with a label, the block takes that label's name.
      - Otherwise B0, B1, ...
    """
    leaders = find_leaders(instrs)
    blocks = []
    label2block: Dict[str, int] = {}

    # map instruction index -> label string if present
    idx_label: Dict[int, str] = {i: ins["label"] for i, ins in enumerate(instrs) if is_label(ins)}

    # compute block ranges
    for bi, start in enumerate(leaders):
        end = (leaders[bi + 1] - 1) if bi + 1 < len(leaders) else len(instrs) - 1
        # strip leading labels inside the block for "instrs" but remember their names
        # official Bril treats labels as pseudo-instructions; we keep them but can skip for analysis
        block_label = idx_label.get(start)
        name = block_label if block_label is not None else f"B{bi}"

        block_instrs = instrs[start:end + 1]
        blocks.append({
            "name": name,
            "start": start,
            "end": end,
            "instrs": block_instrs
        })
        if block_label is not None:
            label2block[block_label] = bi

    # Some labels can appear at non-leader positions (rare if leaders computed correctly); map them too.
    for i, L in idx_label.items():
        # find the block that covers index i
        for bi, b in enumerate(blocks):
            if b["start"] <= i <= b["end"]:
                label2block.setdefault(L, bi)

    return blocks, label2block


def block_successors(blocks: List[Dict[str, Any]], label2block: Dict[str, int]) -> Dict[str, List[str]]:
    """
    Compute successors for each block by inspecting its last *real* instruction.
    Fall-through applies if the last instruction is not a terminator and there is a next block.
    """
    succ: Dict[str, List[str]] = {b["name"]: [] for b in blocks}

    def last_nonlabel_instr(b_instrs: List[Dict[str, Any]]) -> Dict[str, Any]:
        for ins in reversed(b_instrs):
            if not is_label(ins):
                return ins
        return {}

    for i, b in enumerate(blocks):
        name = b["name"]
        last = last_nonlabel_instr(b["instrs"])
        op = last.get("op")

        if op == "jmp":
            for L in target_labels(last):
                bi = label2block.get(L)
                if bi is not None:
                    succ[name].append(blocks[bi]["name"])
        elif op == "br":
            for L in target_labels(last):
                bi = label2block.get(L)
                if bi is not None:
                    succ[name].append(blocks[bi]["name"])
        elif op == "ret":
            # no successors
            pass
        else:
            # fall-through to next block if any instructions exist after this block
            if i + 1 < len(blocks):
                succ[name].append(blocks[i + 1]["name"])

    return succ


def cfg_to_dot(func_name: str, succ: Dict[str, List[str]]) -> str:
    lines = [f'digraph "{func_name}" {{']
    lines.append('  node [shape=rectangle];')
    for src, dsts in succ.items():
        if not dsts:
            # show isolated node
            lines.append(f'  "{src}";')
        else:
            for dst in dsts:
                lines.append(f'  "{src}" -> "{dst}";')
    lines.append("}")
    return "\n".join(lines)


def build_cfg_for_function(fn: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, int], Dict[str, List[str]]]:
    instrs = fn.get("instrs", [])
    blocks, label2block = make_blocks(instrs)
    succ = block_successors(blocks, label2block)
    return blocks, label2block, succ

def main():
    prog = json.load(sys.stdin)

    for fn in prog.get("functions", []):
        name = fn.get("name", "<anon>")
        blocks, label2block, succ = build_cfg_for_function(fn)

        print(f"Function: {name}")
        print("Basic Blocks:")
        for b in blocks:
            print(f"  {b['name']}: instr[{b['start']}..{b['end']}]")
        print("CFG successors:")
        for k, v in succ.items():
            print(f"  {k} -> {v}")
        print()

if __name__ == "__main__":
    main()
