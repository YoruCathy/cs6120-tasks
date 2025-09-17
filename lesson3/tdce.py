#!/usr/bin/env python3

import sys
import json

EFFECT_OPS = {"print", "jmp", "br", "ret", "call", "store", "free"}

def is_effect(instr):
    if "dest" not in instr:
        return True
    op = instr.get("op")
    return op in EFFECT_OPS

def tdce_pass(func):
    instrs = func.get("instrs", [])

    used = set()
    for i in instrs:
        used.update(i.get("args", []))

    new_instrs = []
    for i in instrs:
        if is_effect(i) or i.get("dest") in used:
            new_instrs.append(i)

    changed = len(new_instrs) != len(instrs)
    func["instrs"] = new_instrs
    return changed

def tdce_func(func):
    while tdce_pass(func):
        pass

def tdce_program(prog):
    for f in prog.get("functions", []):
        tdce_func(f)
    return prog

def main():
    prog = json.load(sys.stdin)
    prog = tdce_program(prog)
    json.dump(prog, sys.stdout, indent=2, sort_keys=True)

if __name__ == "__main__":
    main()
