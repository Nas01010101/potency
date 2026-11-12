# Potency

A coding-agent harness for open-source issue fixing, built for Gemma 4 31B. Before the agent submits, Potency lists up to 5 files that the repository's import graph, its commit history before the base commit, and the issue text tie to the files the agent edited. The submission is refused until each listed file is changed or the agent writes one line saying why it needs no change. The answers are rendered as a change report for the maintainer.

The paper is in `paper/potency.md` (PDF: `paper/potency.pdf`).

## Harness layers

| Layer | What Potency does |
|---|---|
| Context before acting | ADK agent: thinking capped at 1,024 tokens, the repository's test command in the prompt (the mini-swe-agent live runs use its default prompt, no cap) |
| Tools | `complete` skill: lists the files tied to the current edit |
| Stopping | binding check at submit (`live/gate_run.py --arm bind`) |
| Output | change report (`python -m potency.report`), with each reason checked by Gemma 4 E4B (`potency/audit.py`) |

Planning and context trimming are those of the underlying single-agent scaffold.

## Why a completion check

On the 71 SWE-bench Verified tasks whose reference fix touches two or more source files, 17 public harnesses edit only some of the needed files in about 70% of runs, and those partial runs resolve at less than half the rate of runs that edit every file:

| Set | Harnesses | Multi-file runs | Partial | Resolve, partial | Resolve, all files edited |
|---|---|---|---|---|---|
| A | 8 (Agentless, AutoCodeRover, SWE-agent, Lingxi, SWE-Exp, FrogBoss, OpenHands, Sonar) | 568 | 72.2% | 26.3% | 59.8% |
| B | 9 open-weight (SWE-RL Llama 3 70B, SWE-Fixer, Devstral, Kimi K2, GLM 4.5/4.6, Qwen3-Coder 30B/480B, Lingxi) | 629 | 70.4% | 22.3% | 53.7% |

Replayed on the unresolved runs that edited a source file and missed a gold file, the gate's top 5 contains a gold file the harness missed in 58.2% (Set A, 354 runs) and 58.0% (Set B, 426 runs) of cases, against 39.8% and 39.9% for BM25 on the issue alone. Fused minus BM25 is +0.184 [0.048, 0.323] and +0.181 [0.055, 0.308] (95% task-clustered bootstrap, 4,000 resamples). Fusion is above BM25 for each of the 17 harnesses (point estimates). These numbers come from `replay/walk.py`, which calls `potency.gate`; `completion_recovery.py` is an earlier standalone version of the same ranking and gives 0.565 and 0.575.

## Layout

| Path | Contents |
|---|---|
| `potency/graphs.py` | co-change index from `git log <base>`, AST import graph, BM25, reciprocal rank fusion |
| `potency/gate.py` | `propose(repo, base, issue, patch, k=5) -> (seeds, files)`; CLI `python -m potency.gate` |
| `potency/report.py` | evidence per listed file, the binding check, and the change report; CLI `python -m potency.report` |
| `potency/audit.py` | reason checker: a small model answers HOLDS or DOUBT for each reason, standard library only |
| `agents/potency/` | Google ADK agent: prompt, sampling (thinking budget 1,024), and the `complete` skill |
| `agents/potency/skills/complete/` | stdlib-only working-tree version of the gate, run by the agent before `submit_patch` |
| `replay/` | `fetch.sh` (data), `harness_premises.py`, `completion_recovery.py`, `per_harness.py`, `walk.py` |
| `bench/` | `missing_file.jsonl` (780 rows) and `score.py` |
| `live/` | live runs with mini-swe-agent and Gemma 4 31B on vLLM (Modal); `bind_summary.py`; `grade_prep.py`, `grade_modal.py` and `graded_summary.py` for SWE-bench grading; `vllm_small.py` and `audit_run.py` for the E4B checker |
| `tests/` | gate, report, scorer and skill tests on a synthetic git repository |

## Use the gate on a repository

```bash
git diff > edit.diff
python -m potency.gate --repo . --base HEAD --issue issue.txt --patch edit.diff
```

## Change report

```bash
python -m potency.report --repo . --base HEAD --issue issue.txt --patch edit.diff --reasons reasons.json
```

`reasons.json` maps a listed path to the reason it was left alone. The command prints a markdown table with one row per listed file (evidence, and edited / left alone with its reason / unanswered) and exits 1 while a file is unanswered, so it can run in CI on a pull request.

## Reason checker

The agent's reasons are its own claims. `potency/audit.py` gives each one to a second, small model with the issue, the diff, and the lines of the skipped file that mention the names the diff touches; the model answers HOLDS or DOUBT. It calls any OpenAI-compatible server (`CHECKER_BASE`, `CHECKER_KEY`, `CHECKER_MODEL`), so a project can run it next to the report in CI. `live/vllm_small.py` serves Gemma 4 E4B on one L40S; `live/audit_run.py` scores the checker on a binding run, counting a reason as wrong when its file is in the reference fix. That label is a proxy: in graded runs, some reasons on reference files come from runs that resolve, so the fix did not need that file.

## Missing-file benchmark

Each row of `bench/missing_file.jsonl` is one unresolved run from a public SWE-bench Verified submission whose patch missed a file of the reference fix: `set`, `harness`, `instance_id`, `repo`, `base_commit`, `edited`, `missing`. 780 rows, 17 harnesses, 69 tasks, 10 Python repositories. A predictions file has one JSON object per line with `set`, `harness`, `instance_id` and `ranked`:

```bash
python bench/score.py preds.jsonl -k 5
```

## One-step ranking against a graph walk

`replay/walk.py` runs a personalized PageRank from the edited files over a graph whose edges carry import links and co-change weights, and compares it with the one-step fused ranking on the benchmark rows.

| Top 5 | Set A | Set B |
|---|---|---|
| Walk, restart 0.5 | 0.384 | 0.415 |
| Walk, restart 0.5, fused with BM25 | 0.585 | 0.624 |
| One-step fusion | 0.582 | 0.580 |
| Walk + BM25 minus one-step [95% CI] | +0.003 [-0.112, +0.108] | +0.045 [-0.044, +0.138] |

The walk is not distinguishable from the one-step ranking, which stays the default.

## Firing rule

The gate fires on every submission. No confidence threshold separated partial from complete runs in the replay (a cutoff of 0.5 on the top co-change score fired on 30% of partial and 22% of complete runs in Set A), so the agent decides which listed files to change.

## Reproduce the replay

```bash
replay/fetch.sh                                     # SWE-bench Verified, 17 submissions, repos (about 2 GB)
uv run --with pandas --with pyarrow replay/harness_premises.py
SETS=data/preds,data/preds_open uv run --with pandas --with pyarrow --with scipy python replay/walk.py   # Tables 3 and 4, both sets
SETS=data/preds,data/preds_open uv run --with pandas --with pyarrow --with scipy python replay/walk.py --summary   # recompute from data/walk_rows.csv
```

`colab/replay.py` runs the same steps on a Colab CPU VM. A rerun there (Python 3.12) gave the same Set A rates (BM25 0.398, fused 0.582 over 354 runs).

## Live runs

On the agent's first submit, `live/gate_run.py` records patch A, then sends one message and allows 20 more steps. Both messages ask the agent to check whether the fix needs changes in other files before resubmitting. The `gate` arm's message lists the gate's files and asks the agent to open and grep each one; the `reflect` arm's message asks it to grep the repository for the names it changed, with no list. Patch B is the last submission. The `bind` arm's message lists each file with its evidence and refuses a resubmission, at most twice, while a listed file has neither a change nor a `REASON <path>: ...` line. `live/bind_summary.py` reports file coverage and the answers.

```bash
VLLM_API_KEY=... modal deploy live/vllm_app.py      # Gemma 4 31B QAT w4a16, vLLM 0.19.1, one H100
MSA=/path/to/mini-swe-agent PYTHONPATH=$MSA VLLM_BASE=https://<your-app>.modal.run \
  python live/gate_run.py --arm gate --workers 20 --out live/runs/gate.jsonl
python live/grade_prep.py live/runs/bind.jsonl live/runs/eval     # first (A) and final (B) patches
uv run --with swebench==4.1.0 --with modal==1.6.4 --with datasets \
  python live/grade_modal.py live/runs/eval/preds_A.jsonl live/runs/eval/gradeA
```

Two servers can share one task list: deploy a second with `APP_NAME=g4-vllm-b modal deploy live/vllm_app.py` and start its client with `--reverse`, which takes tasks from the end. `live/graded_summary.py` joins the grades with the binding run and the E4B audit (resolved first and final patches, and E4B verdicts on reasons split by whether the run resolves).

`live/grade_modal.py` runs each instance's SWE-bench eval script in a Modal sandbox built from the prebuilt `swebench/sweb.eval.*` image and grades the log with swebench's parser; swebench's own Modal runner fails with current Modal (4.1.0 calls a retired sandbox filesystem API, 5.0.2 reads a different dataset schema).

Pinned versions: mini-swe-agent 2.4.6, swebench 4.1.0 (grading), modal 1.6.4, vllm 0.19.1.

## Tests

```bash
uv run --with pytest python -m pytest -q tests
```

## License

MIT
