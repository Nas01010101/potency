import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location("score", pathlib.Path(__file__).parents[1] / "bench" / "score.py")
score = importlib.util.module_from_spec(spec)
spec.loader.exec_module(score)


def row(i, missing):
    return {"set": "a", "harness": "h", "instance_id": i, "missing": missing}


def test_hit_counts_only_first_k_and_missing_rows_score_zero():
    rows = [row("1", ["x.py"]), row("2", ["y.py"]), row("3", ["z.py"])]
    preds = [dict(row("1", []), ranked=["q.py", "x.py"]), dict(row("2", []), ranked=["q.py", "y.py"])]
    assert score.score(rows, preds, k=2) == {"a": (3, 2 / 3)}
    assert score.score(rows, preds, k=1) == {"a": (3, 0.0)}
