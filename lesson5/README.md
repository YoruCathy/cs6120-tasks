# Dominators & Dominance Frontier — Bril Toolkit

This repo contains a tiny toolkit to:

- build a CFG for a Bril function,

- compute dominators (exact assignment pseudocode w/ reverse post-order),

- derive immediate dominators and the dominator tree,

- compute dominance frontiers (walk-up method),

- and visualize everything with GraphViz.

- (Optional) cross-check against NetworkX’s dominance implementation.

It’s designed to be run in a pipeline with bril2json.

# Contents
```
lesson5/
├── dominators.py        # Core algorithms + GraphViz DOT/PNG helpers
└── run_on_bril.py       # Bril adapter (build blocks/CFG) + CLI + NX check
```

# Running
Analyze first function in the file, render PNGs to ./bril_out
`bril2json < benchmarks/core/lcm.bril \
  | python lesson5/run_on_bril.py --nx_check -o bril_out --fmt png --view`


## CLI flags

--func NAME – choose a specific function (default: first)

--nx_check – cross-check dominators/idoms/DF against NetworkX

-o, --outdir DIR – where to write images (default: bril_out)

--fmt {png,svg,pdf} – output format for renders

--view – open the images after rendering

## Outputs

cfg.png – the control-flow graph

dominator_tree.png – the dominator tree

cfg_with_dom.png – CFG with bold idom edges

dominance_frontier.png – CFG with dashed DF edges

ASCII dominator tree printed to stdout
