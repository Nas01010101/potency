"""Grade SWE-bench predictions in Modal sandboxes built from the prebuilt swebench/sweb.eval.* images.

swebench's own Modal runner fails here (5.0.2 at environment setup; 4.1.0 calls the Sandbox
filesystem API that Modal has retired), so this applies each patch and runs the instance's
eval script with plain sandbox exec calls, then grades the log with swebench's own parser.
needs swebench 4.1.0 (5.x reads a different dataset schema). usage: python grade_modal.py preds.jsonl out_dir [--workers 8]  -> out_dir/<id>.log, out_dir/report.json
"""
import argparse, json, pathlib
from concurrent.futures import ThreadPoolExecutor

import modal
from datasets import load_dataset
from swebench.harness.grading import get_eval_report
from swebench.harness.test_spec.test_spec import make_test_spec

APPLY = ('cd /testbed && (git apply -v /tmp/patch.diff || patch --batch --fuzz=5 -p1 -i /tmp/patch.diff) '
         '&& echo POTENCY_APPLIED')


def put(sb, path, text):
    p = sb.exec('bash', '-c', f'cat > {path}')
    p.stdin.write(text.encode())
    p.stdin.write_eof()
    p.stdin.drain()
    p.wait()


def grade(pred, inst, app, out):
    iid = pred['instance_id']
    spec = make_test_spec(inst, namespace='swebench')
    sb = modal.Sandbox.create(image=modal.Image.from_registry(spec.instance_image_key),
                              app=app, timeout=1800, cpu=2, memory=4096)
    try:
        put(sb, '/tmp/patch.diff', pred['model_patch'])
        a = sb.exec('bash', '-c', APPLY)
        a.wait()
        applied = a.stdout.read()
        put(sb, '/eval.sh', spec.eval_script)
        e = sb.exec('bash', '/eval.sh')
        e.wait()
        log = out / f'{iid}.log'
        log.write_text(applied + '\n' + e.stdout.read() + e.stderr.read())
    finally:
        sb.terminate()
    if 'POTENCY_APPLIED' not in applied:
        return iid, {'resolved': False, 'patch_applied': False}
    rep = get_eval_report(spec, pred, str(log), include_tests_status=False)[iid]
    return iid, {'resolved': rep['resolved'], 'patch_applied': rep['patch_successfully_applied']}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('preds')
    ap.add_argument('out')
    ap.add_argument('--workers', type=int, default=8)
    a = ap.parse_args()
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    preds = [json.loads(l) for l in open(a.preds) if l.strip()]
    preds = [p for p in preds if p.get('model_patch')]
    ids = {p['instance_id'] for p in preds}
    insts = {r['instance_id']: r for r in load_dataset('princeton-nlp/SWE-bench_Verified', split='test')
             if r['instance_id'] in ids}
    app = modal.App.lookup('potency-grade', create_if_missing=True)
    results = {}
    with ThreadPoolExecutor(a.workers) as ex:
        futs = [ex.submit(grade, p, insts[p['instance_id']], app, out) for p in preds]
        for f in futs:
            try:
                iid, r = f.result()
            except Exception as err:  # one broken sandbox should not lose the other grades
                iid, r = None, {'error': repr(err)[:300]}
            results[iid or f'error{len(results)}'] = r
            print(iid, r, flush=True)
    (out / 'report.json').write_text(json.dumps(results, indent=1))
    ok = [r for r in results.values() if 'resolved' in r]
    print(f"graded {len(ok)} of {len(preds)}; resolved {sum(r['resolved'] for r in ok)}")


if __name__ == '__main__':
    main()
