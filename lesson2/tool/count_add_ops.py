"""Count the number of add instructions."""
import sys
import json


def count_add_ops(program_data):
    total_add_ops = 0

    for func in program_data["functions"]:
        for ins in func["instrs"]:

            if "op" not in ins:
                continue

            if ins["op"] == "add":
                total_add_ops += 1

    return total_add_ops


if __name__ == "__main__":
    prog = json.load(sys.stdin)
    total_add_ops = count_add_ops(prog)
    print(total_add_ops)
