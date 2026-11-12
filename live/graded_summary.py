"""Join SWE-bench grades with the binding run and the E4B reason audit.

A final patch identical to the first grades the same, so B results default to A (grade_prep.py only
writes B rows that differ). A reason left on a reference-fix file is called right when its run
resolves by the tests and wrong when it does not.
usage: python graded_summary.py runs/bind_all.jsonl runs/audit_all.jsonl runs/eval/gradeA runs/eval/gradeB [more grade dirs...]
Grade dirs whose name contains 'gradeB' hold final patches; the others hold first patches.
"""
import json, sys
from pathlib import Path

bind = [json.loads(l) for l in open(sys.argv[1])]
audit = [json.loads(l) for l in open(sys.argv[2])]
A, B = {}, {}
for d in sys.argv[3:]:
    rep = json.loads((Path(d) / 'report.json').read_text())
    (B if 'gradeB' in Path(d).name else A).update(
        {k: v['resolved'] for k, v in rep.items() if 'resolved' in v})
sub = [r for r in bind if r.get('patch_a')]
graded = [r['instance_id'] for r in sub if r['instance_id'] in A]
fin = {i: B.get(i, A[i]) for i in graded}
gain = [i for i in graded if fin[i] and not A[i]]
loss = [i for i in graded if A[i] and not fin[i]]
print(f'runs {len(bind)}; submitted {len(sub)}; graded {len(graded)}')
print(f'resolved: first patch {sum(A[i] for i in graded)}, final patch {sum(fin.values())}; '
      f'gained {gain}, lost {loss}')
ref = [o for o in audit if o['ref'] and o['instance_id'] in fin]
right = [o for o in ref if fin[o['instance_id']]]
wrong = [o for o in ref if not fin[o['instance_id']]]
oth = [o for o in audit if not o['ref'] and o['instance_id'] in fin]
dz = lambda s: sum(o['verdict'] == 'DOUBT' for o in s)
print(f'reasons on reference files: {len(ref)}; run resolves {len(right)}, does not {len(wrong)}')
print(f'E4B DOUBT: wrong reasons {dz(wrong)}/{len(wrong)}, right reasons on reference files '
      f'{dz(right)}/{len(right)}, other files {dz(oth)}/{len(oth)}')
for o in ref:
    print(f"  {o['instance_id']} {o['file']} resolved={fin[o['instance_id']]} E4B={o['verdict']}")
res_ids = {i for i in graded if fin[i]}
rr = [o for o in audit if o['instance_id'] in res_ids]
ur = [o for o in audit if o['instance_id'] in fin and o['instance_id'] not in res_ids]
print(f'E4B DOUBT rate on all reasons: resolved runs {dz(rr)}/{len(rr)}, unresolved runs {dz(ur)}/{len(ur)}')
