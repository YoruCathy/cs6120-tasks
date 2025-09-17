#!/usr/bin/env python3
import sys
import json

EFFECT_OPS = {"print", "jmp", "br", "ret", "call", "store", "free"}
COMMUTATIVE = {"add", "mul", "and", "or", "xor", "eq"}

def form_blocks(instrs):
    block = []
    for instr in instrs:
        block.append(instr)
        if 'op' in instr and instr['op'] in ('br', 'jmp', 'ret'):
            yield block
            block = []
        elif 'label' in instr and block[:-1]:
            yield block[:-1]
            block = block[-1:]
    if block:
        yield block


def flatten(blocks):
    return [instr for block in blocks for instr in block]



def is_effect(instr):
    return ("dest" not in instr) or (instr.get("op") in EFFECT_OPS)

def will_be_overwritten_later(block, start_idx, name):
    for j in range(start_idx + 1, len(block)):
        if block[j].get("dest") == name:
            return True
    return False

def fresh_var(gen_counter):
    v = f"_lvn{gen_counter[0]}"
    gen_counter[0] += 1
    return v

def normalize_value(instr, var2num):
    op = instr.get("op")
    ty = instr.get("type")
    if op == "const":
        return ("const", ty, instr.get("value"))
    arg_nums = tuple(var2num[a] for a in instr.get("args", []))
    if op == "id":
        return ("id", ty, arg_nums[0] if arg_nums else None)
    if op in COMMUTATIVE:
        arg_nums = tuple(sorted(arg_nums))
    return (op, ty, *arg_nums)

def lvn_block(block, gensym):
    table = {}
    var2num = {}
    num2var = {}
    next_num = [0]

    def ensure_var(v):
        if v in var2num:
            return var2num[v]
        key = ("var", v)
        if key in table:
            num = table[key][0]
        else:
            num = next_num[0]
            next_num[0] += 1
            table[key] = (num, v)
            num2var[num] = v
        var2num[v] = num
        return num

    new_block = []
    for i, instr in enumerate(block):
        if is_effect(instr):
            args = instr.get("args", [])
            if args:
                canon_args = []
                for a in args:
                    num = ensure_var(a)
                    canon_args.append(num2var[num])
                if canon_args != args:
                    instr = dict(instr)
                    instr["args"] = canon_args
            if "dest" in instr:
                dest = instr["dest"]
                num = ensure_var(dest)
                var2num[dest] = num
            new_block.append(instr)
            continue

        args = instr.get("args", [])
        arg_nums = [ensure_var(a) for a in args]
        key = normalize_value(instr, var2num)

        if key in table:
            _, canon_var = table[key]
            dest = instr.get("dest")
            if dest is None:
                new_block.append(instr)
                continue
            if will_be_overwritten_later(block, i, dest):
                tmp = fresh_var(gensym)
                repl = {"op": "id", "type": instr.get("type"), "args": [canon_var], "dest": tmp}
                new_block.append(repl)
                back = {"op": "id", "type": instr.get("type"), "args": [tmp], "dest": dest}
                new_block.append(back)
                num = table[key][0]
                var2num[dest] = num
                num2var[num] = canon_var
            else:
                repl = {"op": "id", "type": instr.get("type"), "args": [canon_var], "dest": dest}
                new_block.append(repl)
                num = table[key][0]
                var2num[dest] = num
            continue

        dest = instr.get("dest")
        if dest is None:
            new_block.append(instr)
            continue

        canon_args = [num2var[n] for n in arg_nums]
        if canon_args != args:
            instr = dict(instr)
            instr["args"] = canon_args

        out_dest = dest
        if will_be_overwritten_later(block, i, dest):
            out_dest = fresh_var(gensym)
            instr = dict(instr)
            instr["dest"] = out_dest

        valnum = next_num[0]
        next_num[0] += 1
        table[key] = (valnum, out_dest)
        num2var[valnum] = out_dest
        var2num[dest] = valnum
        new_block.append(instr)

    block[:] = new_block

def lvn_func(func):
    blocks = list(form_blocks(func["instrs"]))
    gensym = [0]
    for blk in blocks:
        lvn_block(blk, gensym)
    func["instrs"] = flatten(blocks)

def main():
    prog = json.load(sys.stdin)
    for f in prog.get("functions", []):
        lvn_func(f)
    json.dump(prog, sys.stdout, indent=2, sort_keys=True)

if __name__ == "__main__":
    main()
