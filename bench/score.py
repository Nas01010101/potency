"""Score predictions on the missing-file benchmark.

Each line of the predictions file is JSON with the keys set, harness,
instance_id and ranked (a list of file paths, best first). A row is a hit
when one of its first k ranked paths is in the row's missing list.
"""
import argparse
import json
import pathlib


def load(path):
    return [json.loads(l) for l in pathlib.Path(path).read_text().splitlines() if l.strip()]


def key(r):
    return (r["set"], r["harness"], r["instance_id"])


def score(rows, preds, k=5):
    ranked = {key(p): p["ranked"][:k] for p in preds}
    out = {}
    for r in rows:
        hit = bool(set(ranked.get(key(r), [])) & set(r["missing"]))
        n, h = out.get(r["set"], (0, 0))
        out[r["set"]] = (n + 1, h + hit)
    return {s: (n, h / n) for s, (n, h) in out.items()}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("preds")
    ap.add_argument("--bench", default=str(pathlib.Path(__file__).with_name("missing_file.jsonl")))
    ap.add_argument("-k", type=int, default=5)
    a = ap.parse_args()
    for s, (n, rate) in sorted(score(load(a.bench), load(a.preds), a.k).items()):
        print(f"{s}: {n} rows, hit@{a.k} {rate:.3f}")
