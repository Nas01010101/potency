"""Figure 1 of the paper: top-5 hit rate of each ranking on the unresolved runs that missed a reference file.
Values are Table 3 of the replay output (replay/walk.py --summary). usage: python replay/plot_rankers.py assets/replay_rankers.png"""
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROWS = ['Imports', 'History', 'Issue BM25', 'One-step fusion']
SETS = {'Set A (8 harnesses, 354 runs)': ([0.342, 0.362, 0.398, 0.582], '#1F56C4'),
        'Set B (9 open-weight, 426 runs)': ([0.350, 0.378, 0.399, 0.580], '#E8710A')}

plt.rcParams.update({'font.family': 'Helvetica Neue', 'font.size': 11})
fig, ax = plt.subplots(figsize=(7.2, 3.1), dpi=200)
h = 0.36
for j, (name, (vals, c)) in enumerate(SETS.items()):
    ys = [i + (j - 0.5) * (h + 0.04) for i in range(len(ROWS))]
    ax.barh(ys, vals, height=h, color=c, label=name)
    for y, v in zip(ys, vals):
        ax.text(v + 0.006, y, f'{v:.2f}', va='center', fontsize=9.5, color='#333333')
ax.set_yticks(range(len(ROWS)), ROWS)
ax.invert_yaxis()
ax.set_xlim(0, 0.8)
ax.set_xlabel('Share of runs where the top 5 names a reference file the run missed')
for s in ('top', 'right', 'left'):
    ax.spines[s].set_visible(False)
ax.tick_params(axis='y', length=0)
ax.xaxis.grid(True, color='#e6e6e6', linewidth=0.8)
ax.set_axisbelow(True)
ax.annotate('+0.18 over BM25\n95% CI excludes 0 in both sets', xy=(0.585, 3.0), xytext=(0.60, 1.9),
            fontsize=9, color='#333333', ha='left',
            arrowprops=dict(arrowstyle='-', color='#888888', lw=0.8))
ax.legend(frameon=False, loc='lower center', ncol=2, fontsize=9, bbox_to_anchor=(0.5, 1.0))
fig.tight_layout()
fig.savefig(sys.argv[1], facecolor='white')
