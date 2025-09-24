from dataclasses import dataclass, field
from typing import Dict, Set, Tuple, List, Callable, Any, Optional
from collections import defaultdict, deque

@dataclass
class Statement:
    text: str
    def defs(self) -> Set[str]:
        t = self.text.strip()
        if "=" in t:
            lhs, rhs = [p.strip() for p in t.split("=", 1)]
            if lhs.startswith("*") or lhs.startswith("["):
                return set()
            return {lhs}
        return set()
    def uses(self) -> Set[str]:
        t = self.text.strip()
        if "=" not in t: return set()
        lhs, rhs = [p.strip() for p in t.split("=", 1)]
        if lhs.startswith("*") or lhs.startswith("["):
            return self._vars_in(lhs) | self._vars_in(rhs)
        return self._vars_in(rhs)
    @staticmethod
    def _vars_in(expr: str) -> Set[str]:
        import re
        expr = expr.replace("[", " ").replace("]", " ").replace("*", " ")
        tokens = re.findall(r"[A-Za-z_]\w*", expr)
        return set(tokens)

@dataclass
class BasicBlock:
    bid: str
    stmts: List[Statement] = field(default_factory=list)
    preds: Set[str] = field(default_factory=set)
    succs: Set[str] = field(default_factory=set)
    def block_uses_defs(self):
        seen_defs=set(); use=set(); defs=set()
        for s in self.stmts:
            u=s.uses(); use|={v for v in u if v not in seen_defs}
            d=s.defs(); defs|=d; seen_defs|=d
        return use, defs

@dataclass
class CFG:
    blocks: Dict[str, BasicBlock]
    entry: str
    exit: str

def make_cfg(blocks: Dict[str, List[str]], edges: List[Tuple[str, str]], entry: str, exit: str) -> CFG:
    bmap={bid: BasicBlock(bid, [Statement(t) for t in stmts]) for bid, stmts in blocks.items()}
    for u,v in edges:
        bmap[u].succs.add(v); bmap[v].preds.add(u)
    return CFG(bmap, entry, exit)

Direction = str

@dataclass
class DataflowProblem:
    direction: Direction
    top: Any
    meet: Callable[[List[Any]], Any]
    transfer: Callable[[BasicBlock, Any], Any]
    init_map: Optional[Dict[str, Any]] = None

def worklist_solve(cfg: CFG, prob: DataflowProblem):
    blocks=cfg.blocks; in_map={}; out_map={}
    for bid in blocks:
        in_map[bid]=prob.top; out_map[bid]=prob.top
    if prob.init_map:
        for k,v in prob.init_map.items():
            if k in in_map: in_map[k]=v
            if k in out_map: out_map[k]=v
    from collections import deque
    wl=deque(blocks.keys())
    while wl:
        b=wl.popleft(); blk=blocks[b]
        if prob.direction=="forward":
            in_val = prob.meet([out_map[p] for p in blk.preds]) if blk.preds else in_map[b]
            out_val = prob.transfer(blk, in_val)
            changed = out_val != out_map[b]
            in_map[b]=in_val; out_map[b]=out_val
            if changed:
                for s in blk.succs: wl.append(s)
        elif prob.direction=="backward":
            out_val = prob.meet([in_map[s] for s in blk.succs]) if blk.succs else out_map[b]
            in_val = prob.transfer(blk, out_val)
            changed = in_val != in_map[b]
            out_map[b]=out_val; in_map[b]=in_val
            if changed:
                for p in blk.preds: wl.append(p)
        else:
            raise ValueError("direction must be 'forward' or 'backward'")
    return in_map, out_map

# Reaching Definitions
DefSite = Tuple[str, int, str]

def compute_def_sites(cfg: CFG) -> Dict[str, Set[DefSite]]:
    var2sites=defaultdict(set)
    for bid, blk in cfg.blocks.items():
        for i, s in enumerate(blk.stmts):
            for v in s.defs(): var2sites[v].add((bid,i,v))
    return var2sites

def reaching_definitions_problem(cfg: CFG) -> DataflowProblem:
    var2sites=compute_def_sites(cfg)
    gen={}; kill={}
    for bid, blk in cfg.blocks.items():
        gen_b=[]; seen=set()
        for i, s in enumerate(blk.stmts):
            for v in s.defs():
                if v in seen: gen_b=[site for site in gen_b if site[2]!=v]
                gen_b.append((bid,i,v)); seen.add(v)
        gen[bid]=set(gen_b)
        kill_vars={site[2] for site in gen_b}
        kill[bid]=set().union(*[var2sites[v] for v in kill_vars]) - gen[bid]
    def meet(sets): 
        out=set()
        for s in sets: out|=s
        return out
    def transfer(blk, IN): return gen[blk.bid] | (IN - kill[blk.bid])
    return DataflowProblem(direction="forward", top=set(), meet=meet, transfer=transfer, init_map={cfg.entry:set()})

# Live Variables
def live_variables_problem(cfg: CFG) -> DataflowProblem:
    use_b={}; def_b={}
    for bid, blk in cfg.blocks.items():
        u,d=blk.block_uses_defs(); use_b[bid]=u; def_b[bid]=d
    def meet(sets):
        out=set()
        for s in sets: out|=s
        return out
    def transfer(blk, OUT): return use_b[blk.bid] | (OUT - def_b[blk.bid])
    return DataflowProblem(direction="backward", top=set(), meet=meet, transfer=transfer, init_map={cfg.exit:set()})
