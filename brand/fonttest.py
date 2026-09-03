import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, findfont

samples = [
    ("Bahnschrift", "normal"),
    ("Bahnschrift", "bold"),
    ("Franklin Gothic Medium", "normal"),
    ("Segoe UI", "bold"),
    ("Arial", "bold"),
    ("Cascadia Mono", "normal"),
    ("Consolas", "normal"),
]
W, H = 1200, 90*len(samples)+40
fig = plt.figure(figsize=(W/100, H/100), dpi=100)
ax = fig.add_axes([0,0,1,1]); ax.set_xlim(0,W); ax.set_ylim(H,0); ax.axis('off')
fig.patch.set_facecolor('white')
for i,(fam,w) in enumerate(samples):
    fp = FontProperties(family=fam, weight=w, size=30)
    y = 60+i*90
    ax.text(20, y, "HAZARD WATCH  H×E×V=Loss  1 128×191", fontproperties=fp, va='baseline')
    ax.text(20, y+28, f"{fam} {w} -> {findfont(fp).split(chr(92))[-1]}",
            fontproperties=FontProperties(family='DejaVu Sans', size=9), va='baseline', color='#888')
fig.savefig(r"fonttest.png", dpi=100)
print("ok")
