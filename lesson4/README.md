# Lesson 4 Task Implementation

This repository contains my implementation of copy-aware reaching definitions analysis for Bril programs.
The analysis constructs basic blocks, computes predecessors/successors, and then applies a worklist algorithm to propagate reaching definitions across the control-flow graph. It also handles copy operations (id) in a flow-sensitive manner.

# Files

- rd.py – main script containing the analysis.

- tests/ – Bril programs used for testing the analysis.

## Running the Analysis

You can run the analysis directly on a Bril JSON program:

`bril2json < tests/example.bril | python3 rd.py`


This will print the in and out sets of definitions for each basic block.

## Testing with turnt

The testing harness is set up with turnt
, which runs the analysis against the provided .bril test cases.

Generate expected outputs
Run the following once to save the expected outputs for all test cases:

`turnt --save tests/*.bril`


Re-run tests for regression checking
To compare your current implementation with the saved outputs:

`turnt tests/*.bril`

## Notes

Terminators recognized: br, jmp, ret.

Copy propagation: handled explicitly for id operations.

Outputs show definitions reaching the entry (in) and exit (out) of each block.