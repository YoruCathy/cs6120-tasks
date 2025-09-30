from typing import Dict, Set, List, Optional
from graphviz import Source
import os
from collections import deque

class CFG:
    def __init__(self, entry: str):
        self.entry = entry
        # Map: node -> set of predecessor nodes
        self.blocks: Dict[str, Set[str]] = {}

    def add_block(self, name: str):
        if name not in self.blocks:
            self.blocks[name] = set()

    def add_edge(self, u: str, v: str):
        """Add edge u -> v (records v's predecessor u)."""
        self.add_block(u)
        self.add_block(v)
        self.blocks[v].add(u)

    # convenience: derive succs for reachability/pruning
    def succs(self) -> Dict[str, Set[str]]:
        s: Dict[str, Set[str]] = {n: set() for n in self.blocks}
        for v, preds in self.blocks.items():
            for p in preds:
                s.setdefault(p, set()).add(v)
        for n in self.blocks:
            s.setdefault(n, set())
        return s

def _reachable_from_entry(cfg: CFG) -> Set[str]:
    """Forward BFS over succs to find nodes reachable from entry."""
    succs = cfg.succs()
    seen: Set[str] = set()
    q = deque([cfg.entry])
    while q:
        n = q.popleft()
        if n in seen: 
            continue
        seen.add(n)
        for s in succs.get(n, ()):
            if s not in seen:
                q.append(s)
    return seen

def _prune_unreachable(cfg: CFG) -> None:
    keep = _reachable_from_entry(cfg)
    # prune blocks and preds not in keep
    cfg.blocks = {n: (preds & keep) for n, preds in cfg.blocks.items() if n in keep}

# --------------------------- Dominators core --------------------------- #

def compute_dominators(cfg: CFG) -> Dict[str, Set[str]]:
    # be robust to dead blocks
    _prune_unreachable(cfg)

    blocks = list(cfg.blocks.keys())
    dom: Dict[str, Set[str]] = {b: set(blocks) for b in blocks}
    dom[cfg.entry] = {cfg.entry}

    changed = True
    while changed:
        changed = False
        for v in blocks:
            if v == cfg.entry:
                continue
            preds = cfg.blocks[v]
            if preds:
                new_set = {v}.union(set.intersection(*(dom[p] for p in preds)))
            else:
                new_set = {v}
            if new_set != dom[v]:
                dom[v] = new_set
                changed = True
    return dom

def immediate_dominators(dom, entry):
    idom = {}
    for v, D in dom.items():
        if v == entry:
            idom[v] = None   # or entry, just be consistent
            continue
        strict = D - {v}
        imm = None
        for d in strict:
            others = strict - {d}
            if all(o in dom[d] for o in others):
                imm = d
                break
        if imm is None and strict:
            imm = max(strict, key=lambda x: len(dom[x]))
        idom[v] = imm
    return idom


def dominator_tree(idom: Dict[str, Optional[str]]) -> Dict[str, List[str]]:
    tree: Dict[str, List[str]] = {n: [] for n in idom}
    for n, p in idom.items():
        if p is not None:
            tree[p].append(n)
    for k in tree:
        tree[k].sort()
    return tree

def dominance_frontier(cfg: CFG, idom: Dict[str, Optional[str]]) -> Dict[str, Set[str]]:
    DF: Dict[str, Set[str]] = {n: set() for n in idom}
    for y, preds in cfg.blocks.items():
        if len(preds) < 2:
            continue
        for p in preds:
            runner = p
            stop = idom[y]
            while runner is not None and runner != stop:
                DF[runner].add(y)
                runner = idom[runner]
    return DF

# --------------------------- Visualization --------------------------- #

def _cfg_succs(cfg: CFG) -> Dict[str, Set[str]]:
    return cfg.succs()

def to_dot_cfg(cfg: CFG) -> str:
    succs = _cfg_succs(cfg)
    lines = ["digraph CFG {", "  rankdir=LR;", "  node [shape=box];"]
    for n in cfg.blocks:
        shape = "doublecircle" if n == cfg.entry else "box"
        lines.append(f'  "{n}" [shape={shape}];')
    for u, vs in succs.items():
        for v in vs:
            lines.append(f'  "{u}" -> "{v}";')
    lines.append("}")
    return "\n".join(lines)

def to_dot_dominator_tree(idom: Dict[str, Optional[str]]) -> str:
    tree = dominator_tree(idom)
    lines = ["digraph DomTree {", "  rankdir=TB;", "  node [shape=ellipse];"]
    for p, kids in tree.items():
        for c in kids:
            lines.append(f'  "{p}" -> "{c}" [penwidth=2];')
    lines.append("}")
    return "\n".join(lines)

def to_dot_cfg_with_dom(idom: Dict[str, Optional[str]], cfg: CFG) -> str:
    succs = _cfg_succs(cfg)
    lines = ["digraph CFGDom {", "  rankdir=LR;", "  node [shape=box];"]
    for n in cfg.blocks:
        shape = "doublecircle" if n == cfg.entry else "box"
        lines.append(f'  "{n}" [shape={shape}];')
    for u, vs in succs.items():
        for v in vs:
            lines.append(f'  "{u}" -> "{v}" [color=gray];')
    for n, p in idom.items():
        if p is not None:
            lines.append(f'  "{p}" -> "{n}" [color=black, penwidth=2];')
    lines.append("}")
    return "\n".join(lines)

def to_dot_dominance_frontier(cfg: CFG, df: Dict[str, Set[str]]) -> str:
    succs = _cfg_succs(cfg)
    lines = ["digraph DF {", "  rankdir=LR;", "  node [shape=box];"]
    for n in cfg.blocks:
        shape = "doublecircle" if n == cfg.entry else "box"
        lines.append(f'  "{n}" [shape={shape}];')
    for u, vs in succs.items():
        for v in vs:
            lines.append(f'  "{u}" -> "{v}" [color=gray];')
    for a, bs in df.items():
        for b in bs:
            lines.append(f'  "{a}" -> "{b}" [style=dashed, label="DF"];')
    lines.append("}")
    return "\n".join(lines)

def ascii_dom_tree(idom: Dict[str, Optional[str]], root: Optional[str] = None) -> str:
    tree = dominator_tree(idom)
    if root is None:
        roots = [n for n, p in idom.items() if p is None]
        root = roots[0] if roots else None
    lines: List[str] = []
    def dfs(n: str, prefix: str = ""):
        lines.append(prefix + n)
        for i, c in enumerate(tree.get(n, [])):
            last = (i == len(tree.get(n, [])) - 1)
            branch = "└─ " if last else "├─ "
            dfs(c, prefix + branch)
    if root is not None:
        dfs(root)
    return "\n".join(lines)

def render_dot(dot: str, out_path_noext: str, fmt: str = "png", view: bool = False) -> None:
    src = Source(dot)
    src.render(out_path_noext, format=fmt, view=view, cleanup=True)

def render_all_graphs(cfg: CFG, idom: Dict[str, Optional[str]], df: Dict[str, Set[str]],
                      out_dir: str = ".", fmt: str = "png", view: bool = False) -> None:
    os.makedirs(out_dir, exist_ok=True)
    render_dot(to_dot_cfg(cfg), f"{out_dir}/cfg", fmt=fmt, view=view)
    render_dot(to_dot_dominator_tree(idom), f"{out_dir}/dominator_tree", fmt=fmt, view=view)
    render_dot(to_dot_cfg_with_dom(idom, cfg), f"{out_dir}/cfg_with_dom", fmt=fmt, view=view)
    render_dot(to_dot_dominance_frontier(cfg, df), f"{out_dir}/dominance_frontier", fmt=fmt, view=view)
