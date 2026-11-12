"""Gemma 4 31B first patch (before the check) vs final patch with Potency, 31 graded runs. usage: plot_base_vs_potency.py out.png"""
import sys
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
plt.rcParams.update({'font.family': 'Helvetica Neue', 'font.size': 12})
fig, ax = plt.subplots(figsize=(8.2, 3.8), dpi=200)
labels = ['Tasks resolved\n(of 31 graded)', 'Missed reference files\nthe check listed: answered\n(of 12)', 'All listed files answered\nfor the maintainer\n(of 155)']
base, pot = [(10, 31), (0, 12), (0, 155)], [(10, 31), (12, 12), (150, 155)]
for i in range(3):
    for off, (n, d), c, lab in ((-0.2, base[i], '#E8710A', 'Gemma 4 31B, first patch'), (0.2, pot[i], '#1F56C4', 'Gemma 4 31B + Potency, final patch')):
        ax.bar(i + off, 100 * n / d, 0.38, color=c, label=lab if i == 0 else None)
        ax.text(i + off, 100 * n / d + 2, f'{n}/{d}', ha='center', color='#333')
ax.set_xticks(range(3), labels, fontsize=10.5); ax.set_ylim(0, 115); ax.set_ylabel('Share (%)')
for s in ('top', 'right'): ax.spines[s].set_visible(False)
ax.yaxis.grid(True, color='#e6e6e6'); ax.set_axisbelow(True)
ax.legend(loc='lower center', ncol=2, bbox_to_anchor=(0.5, 1.0), frameon=False, fontsize=11)
fig.tight_layout(); fig.savefig(sys.argv[1], facecolor='white')
