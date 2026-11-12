"""Write SWE-bench prediction files for the first (A) and final (B) patch of a binding run.

B rows are only written where the final patch differs from the first, since an
unchanged patch grades the same.
"""
import json
import sys

src, out_dir = sys.argv[1], sys.argv[2]
rows = [json.loads(line) for line in open(src)]
n_a = n_b = 0
with open(f"{out_dir}/preds_A.jsonl", "w") as fa, open(f"{out_dir}/preds_B.jsonl", "w") as fb:
    for r in rows:
        a, b = r.get("patch_a") or "", r.get("patch_b") or ""
        if a:
            fa.write(json.dumps({"instance_id": r["instance_id"], "model_name_or_path": "bind-A", "model_patch": a}) + "\n")
            n_a += 1
        if b and b != a:
            fb.write(json.dumps({"instance_id": r["instance_id"], "model_name_or_path": "bind-B", "model_patch": b}) + "\n")
            n_b += 1
print(f"{len(rows)} runs; A patches {n_a}; B patches that differ from A {n_b}")
