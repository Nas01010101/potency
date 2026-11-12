"""Resolve rate of multi-file runs: partial edits vs every reference file edited. usage: plot_premise.py out.png"""
import sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family': 'Helvetica Neue', 'font.size': 13})
fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)
sets = ['Set A\n8 harnesses, 568 runs', 'Set B\n9 open-weight, 629 runs']
part, full = [26.3, 22.3], [59.8, 53.7]
for i in range(2):
    b1 = ax.bar(i - 0.2, part[i], 0.38, color='#E8710A', label='Some reference files edited' if i == 0 else None)
    b2 = ax.bar(i + 0.2, full[i], 0.38, color='#1F56C4', label='Every reference file edited' if i == 0 else None)
    ax.text(i - 0.2, part[i] + 1.2, f'{part[i]}%', ha='center', color='#333')
    ax.text(i + 0.2, full[i] + 1.2, f'{full[i]}%', ha='center', color='#333')
    ax.text(i, full[i] + 8, f'{full[i] / part[i]:.1f}x', ha='center', fontsize=15, fontweight='bold', color='#333')
ax.set_xticks([0, 1], sets); ax.set_ylim(0, 80); ax.set_ylabel('Tasks resolved (%)')
for s in ('top', 'right'): ax.spines[s].set_visible(False)
ax.yaxis.grid(True, color='#e6e6e6'); ax.set_axisbelow(True)
ax.legend(loc='lower center', ncol=2, bbox_to_anchor=(0.5, 1.0), frameon=False, fontsize=11)
fig.tight_layout(); fig.savefig(sys.argv[1], facecolor='white')
