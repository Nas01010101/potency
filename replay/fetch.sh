#!/usr/bin/env bash
# Downloads the replay inputs into data/: SWE-bench Verified, the 17 harness submissions
# (predictions from the public S3 bucket, resolved ids from SWE-bench/experiments), and the
# upstream repositories at full history. Needs aws-cli (no credentials) and git. About 2 GB.
set -euo pipefail
cd "$(dirname "$0")/.."
SET_A="20241202_agentless-1.5_claude-3.5-sonnet-20241022 20250122_autocoderover-v2.1-claude-3-5-sonnet-20241022
20250522_sweagent_claude-4-sonnet-20250514 20250720_Lingxi-v1.5_claude-4-sonnet-20250514 20250806_SWE-Exp_DeepSeek-V3
20251110_frogboss-32b 20251127_openhands_claude-opus-4-5 20251205_sonar-foundation-agent_claude-opus-4-5"
SET_B="20250226_swerl_llama3_70b 20250306_SWE-Fixer_Qwen2.5-7b-retriever_Qwen2.5-72b-editor
20250520_openhands_devstral_small 20250716_openhands_kimi_k2 20250728_zai_glm4-5
20250805_openhands-Qwen3-Coder-30B-A3B-Instruct 20250805_openhands-Qwen3-Coder-480B-A35B-Instruct
20250930_zai_glm4-6 20251014_Lingxi_kimi_k2"
VERIFIED=https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified/resolve/main/data/test-00000-of-00001.parquet
EXP=https://raw.githubusercontent.com/SWE-bench/experiments/main/evaluation/verified

get() {   # $1 = output dir, rest = run names
  local out=$1; shift; mkdir -p "$out"
  curl -sSL "$VERIFIED" -o "$out/verified.parquet"
  for r in "$@"; do
    local s3="s3://swe-bench-submissions/verified/$r"
    if ! aws s3 cp --no-sign-request --quiet "$s3/all_preds.jsonl" "$out/$r.jsonl" 2>/dev/null &&
       # Qwen3-Coder runs sit under <date>-<name> on S3, not <date>_<name> (see their metadata.yml)
       ! aws s3 cp --no-sign-request --quiet "s3://swe-bench-submissions/verified/${r/_/-}/all_preds.jsonl" "$out/$r.jsonl" 2>/dev/null; then
      # some submissions (SWE-RL) publish only per-instance logs/<id>/patch.diff
      aws s3 sync --no-sign-request --quiet "$s3/logs/" "$out/.logs_$r" --exclude '*' --include '*/patch.diff'
      python3 - "$out/.logs_$r" "$out/$r.jsonl" <<'EOF'
import json, os, sys
d, o = sys.argv[1:]
with open(o, 'w') as f:
    for i in sorted(os.listdir(d)):
        f.write(json.dumps({'instance_id': i, 'model_patch': open(os.path.join(d, i, 'patch.diff')).read()}) + '\n')
EOF
    fi
    curl -sSfL "$EXP/$r/results/results.json" -o "$out/$r.results.json"
  done
}
get data/preds $SET_A
get data/preds_open $SET_B

mkdir -p data/repos
python3 -c "import pandas as pd; print('\n'.join(sorted(set(pd.read_parquet('data/preds/verified.parquet').repo))))" |
while read -r repo; do
  [ -d "data/repos/${repo#*/}" ] || git clone -q "https://github.com/$repo" "data/repos/${repo#*/}"
done
