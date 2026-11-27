"""钉钉文档用的三张图（第 2 版）。中文用冬青黑体，英文和数字用 Helvetica Neue；图内不用全角标点。
用法：envs/plot/bin/python dingdoc/figs.py"""
import os
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager as fm
from matplotlib.patches import FancyBboxPatch, Rectangle
OUT = os.path.dirname(os.path.abspath(__file__))
for f in ("/System/Library/Fonts/Hiragino Sans GB.ttc", "/System/Library/Fonts/HelveticaNeue.ttc"): fm.fontManager.addfont(f)
BG = "#ffffff"
plt.rcParams.update({"font.family": ["Helvetica Neue", "Hiragino Sans GB"], "axes.unicode_minus": False, "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG})
INK, SUB, MUTE, GRID, GREY = "#1f1f1e", "#52514e", "#8a8983", "#e6e5e1", "#b9b8b2"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"; BLUE_BG, ORANGE_BG, AQUA_BG = "#eaf2fc", "#fdeee8", "#e6f6ef"

# ───────── 图 1：同一条规范，两种后续，左右对照（函数命名的例子） ─────────
from matplotlib.patches import Circle, FancyArrowPatch
import matplotlib.patheffects as pe
fm.fontManager.addfont("/System/Library/Fonts/Menlo.ttc")
BL, OR, OKC, NOC, DARK = "#1c5cab", "#b8491f", "#1baf7a", "#d9534f", "#232322"
FW, FH = 10.0, 6.9
fig = plt.figure(figsize=(FW, FH)); ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, FW); ax.set_ylim(0, FH); ax.axis("off")
def rbox(x, y, w, h, fc, ec="none", lw=0, r=0.12, z=2): ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle=f"round,pad=0,rounding_size={r}", lw=lw, ec=ec, fc=fc, zorder=z))
def shadow(x, y, w, h, r=0.12):
    for d, a in ((0.07, 0.05), (0.04, 0.07)): ax.add_patch(FancyBboxPatch((x + 0.01, y - d), w, h, boxstyle=f"round,pad=0,rounding_size={r}", lw=0, fc="#000000", alpha=a, zorder=1))
def txt(x, y, t, size, color=INK, ha="left", bold=False, z=5):
    o = ax.text(x, y, t, fontsize=size, color=color, ha=ha, va="center", zorder=z)
    if bold: o.set_path_effects([pe.withStroke(linewidth=size * 0.036, foreground=color)])
def code(x, y, t, fc, color, size=12.5):
    w = 0.26 + len(t) * 0.602 * size / 72; rbox(x, y - 0.2, w, 0.4, fc, r=0.08, z=4)
    ax.text(x + w / 2, y - 0.005, t, fontsize=size, color=color, ha="center", va="center", family="Menlo", zorder=5); return w
def pill(x, y, t, fc, size=12):
    w = 0.34 + size / 72 * 1.0 * len(t); rbox(x, y - 0.2, w, 0.4, fc, r=0.2, z=4); txt(x + w / 2, y, t, size, "#ffffff", "center", True); return w
def arr(x1, y1, x2, y2, c): ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>,head_width=3.4,head_length=6", color=c, lw=2, shrinkA=0, shrinkB=0, zorder=3))
def mark(x, y, ok):
    ax.add_patch(Circle((x, y), 0.16, fc=OKC if ok else NOC, ec="none", zorder=4))
    if ok: ax.plot([x - 0.075, x - 0.022, x + 0.08], [y, y - 0.06, y + 0.065], color="#ffffff", lw=2.2, solid_capstyle="round", solid_joinstyle="round", zorder=5)
    else:
        for d in (1, -1): ax.plot([x - 0.06, x + 0.06], [y - 0.06 * d, y + 0.06 * d], color="#ffffff", lw=2.2, solid_capstyle="round", zorder=5)
def band_card(x, y, w, h, hh, color):
    shadow(x, y, w, h); rbox(x, y, w, h, color); rbox(x + 0.035, y + 0.035, w - 0.07, h - hh - 0.035, "#ffffff", r=0.09, z=3)
    ax.add_patch(Rectangle((x + 0.035, y + 0.2), w - 0.07, h - hh - 0.2, fc="#ffffff", ec="none", zorder=3))
LX, RX, CW = 0.4, 5.2, 4.4; LC, RC = LX + CW / 2, RX + CW / 2
# 标题
E = 18 / 72
txt(0.4, 6.48, "同样是后来的一句话", 18, INK, bold=True); txt(0.4 + 9 * E + 0.22, 6.48, "有的要跟", 18, BLUE, bold=True); txt(0.4 + 13 * E + 0.44, 6.48, "有的不能跟", 18, ORANGE, bold=True)
# 团队规范
shadow(2.45, 5.2, 5.1, 0.78); rbox(2.45, 5.2, 5.1, 0.78, DARK)
txt(2.75, 5.59, "团队规范", 11.5, "#a9a8a2"); txt(3.72, 5.59, "函数名用下划线", 15, "#ffffff", bold=True); code(5.4, 5.59, "get_user", "#454543", "#ffffff", 13)
# 分叉
ax.plot([5, 5], [5.2, 4.9], color=GREY, lw=2, zorder=1, solid_capstyle="round")
ax.plot([5, LC, LC], [4.9, 4.9, 4.72], color=BLUE, lw=2, zorder=1, solid_joinstyle="round"); ax.plot([5, RC, RC], [4.9, 4.9, 4.72], color=ORANGE, lw=2, zorder=1, solid_joinstyle="round")
arr(LC, 4.75, LC, 4.52, BLUE); arr(RC, 4.75, RC, 4.52, ORANGE)
ax.text(5, 4.9, "后来  维护者又说了一句", fontsize=12, color=SUB, ha="center", va="center", zorder=6, bbox=dict(fc=BG, ec="none", pad=5))
# 两种后续
for x, name, scope, quote, chipt, ink, c, bg in ((LX, "正式修改", "对所有人算数", "团队商定  以后统一用驼峰", "getUser", BL, BLUE, BLUE_BG), (RX, "个人破例", "只对他自己算数", "我这个临时脚本  名字随便起", None, OR, ORANGE, ORANGE_BG)):
    shadow(x, 3.2, CW, 1.3); rbox(x, 3.2, CW, 1.3, bg); ax.add_patch(FancyBboxPatch((x, 3.2), 0.09, 1.3, boxstyle="round,pad=0,rounding_size=0.045", lw=0, fc=c, zorder=3))
    w = pill(x + 0.32, 4.14, name, c); txt(x + 0.32 + w + 0.16, 4.14, scope, 12.5, ink)
    txt(x + 0.32, 3.56, quote, 14.5, INK)
    if chipt: code(x + 0.32 + 12 * 14.5 / 72 + 0.12, 3.56, chipt, "#ffffff", BL, 13)
    arr(x + CW / 2, 3.18, x + CW / 2, 2.98, c)
# 记忆系统
rbox(LX, 2.5, RX + CW - LX, 0.46, "#efeeea", r=0.23)
txt((LX + RX + CW) / 2, 2.73, "后来的成员没听过这些话    只能靠记忆系统知道", 12.5, SUB, "center")
# 结果
rows = ((LX, "跟上", "规范变了  要跟着改", ("getUser", "改用新写法"), ("get_user", "还按旧的写"), BLUE, BLUE_BG, BL), (RX, "守住", "规范没变  不能跟着改", ("get_user", "仍按团队规范"), ("tmp1", "也跟着随便起"), ORANGE, ORANGE_BG, OR))
for x, word, why, good, bad, c, bg, ink in rows:
    arr(x + CW / 2, 2.48, x + CW / 2, 2.28, c)
    band_card(x, 0.3, CW, 1.95, 0.66, c)
    txt(x + 0.32, 1.915, word, 19, "#ffffff", bold=True); txt(x + 1.2, 1.9, why, 12.5, "#ffffff")
    mark(x + 0.5, 1.2, True); w = code(x + 0.85, 1.2, good[0], bg, ink, 13); txt(x + 0.85 + w + 0.18, 1.2, good[1], 13.5, INK)
    mark(x + 0.5, 0.68, False); w = code(x + 0.85, 0.68, bad[0], "#f1f1ee", MUTE, 13); txt(x + 0.85 + w + 0.18, 0.68, bad[1], 13.5, MUTE)
fig.savefig(f"{OUT}/fig1_流程.png", dpi=200); plt.close(fig)

DATA = [("无记忆", 23, 6, 41), ("Graphiti", 25, 14, 37), ("Mem0", 37, 30, 44), ("Cognee", 38, 29, 46), ("Hindsight", 42, 32, 52),
        ("RAG", 44, 50, 39), ("LangMem", 49, 50, 48), ("EverOS", 54, 85, 22), ("理想送达", 99, 100, 98)]
REF = {"无记忆": "下限", "理想送达": "上限"}

# ───────── 图 2：遵守率 ─────────
fig, ax = plt.subplots(figsize=(9.2, 5.0)); fig.subplots_adjust(left=0.2, right=0.95, top=0.84, bottom=0.14)
for i, (n, v, _a, _b) in enumerate(DATA):
    ax.barh(i, v, height=0.6, color=GREY if n in REF else BLUE)
    ax.text(v + 1.6, i, f"{v}%", va="center", fontsize=11.5, color=INK)
    ax.text(-2.2, i, n, va="center", ha="right", fontsize=11.5, color=INK)
    if n in REF: ax.text(-2.2 - (5.4 if n == "无记忆" else 7.2) * 1.55, i, REF[n], va="center", ha="right", fontsize=9.5, color=MUTE)
ax.set_xlim(0, 108); ax.set_ylim(-0.6, len(DATA) - 0.4); ax.set_yticks([]); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0", "25%", "50%", "75%", "100%"], fontsize=10, color=MUTE)
ax.xaxis.grid(True, color=GRID, lw=1); ax.set_axisbelow(True); ax.tick_params(length=0, pad=6)
for s in ax.spines.values(): s.set_visible(False)
fig.text(0.04, 0.93, "遵守率  记忆系统都远低于上限", fontsize=14, color=INK, va="center")
fig.text(0.04, 0.04, "32 组  13 条规范  每个对照组约 507 个判分点", fontsize=10, color=MUTE, va="center")
fig.savefig(f"{OUT}/fig2_遵守率.png", dpi=200); plt.close(fig)

# ───────── 图 3：跟上 和 守住 ─────────
fig, ax = plt.subplots(figsize=(7.6, 6.6)); fig.subplots_adjust(left=0.13, right=0.95, top=0.88, bottom=0.12)
ax.add_patch(Rectangle((50, 50), 55, 55, fc="#f3f8f5", ec="none", zorder=0))
for v in (0, 25, 50, 75, 100): ax.plot([v, v], [0, 105], color=GRID, lw=1, zorder=1); ax.plot([0, 105], [v, v], color=GRID, lw=1, zorder=1)
ax.plot([50, 50], [0, 105], color=GREY, lw=1.2, zorder=1); ax.plot([0, 105], [50, 50], color=GREY, lw=1.2, zorder=1)
OFF = {"无记忆": (0, 11, "center", "bottom"), "Graphiti": (10, -3, "left", "top"), "Mem0": (10, -5, "left", "top"), "Cognee": (-11, 0, "right", "center"), "Hindsight": (9, 6, "left", "bottom"),
       "RAG": (11, -2, "left", "center"), "LangMem": (11, -4, "left", "center"), "EverOS": (0, 12, "center", "bottom"), "理想送达": (-12, 0, "right", "center")}
for n, _c, a, b in DATA:
    ax.scatter([a], [b], s=110, color=GREY if n in REF else BLUE, edgecolor=BG, linewidth=2, zorder=3)
    dx, dy, ha, va = OFF[n]; ax.annotate(n, (a, b), xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=11.5, color=INK, zorder=4)
ax.text(77.5, 77, "目标  两边都做对", fontsize=10.5, color="#3d7d62", ha="center", va="center")
ax.text(77.5, 6, "只信最新一句", fontsize=10.5, color=MUTE, ha="center", va="center"); ax.text(25, 96, "从不更新", fontsize=10.5, color=MUTE, ha="center", va="center")
ax.set_xlim(0, 105); ax.set_ylim(0, 105); ax.set_xticks([0, 25, 50, 75, 100]); ax.set_yticks([25, 50, 75, 100])
ax.set_xticklabels(["0", "25%", "50%", "75%", "100%"], fontsize=10, color=MUTE); ax.set_yticklabels(["25%", "50%", "75%", "100%"], fontsize=10, color=MUTE)
ax.set_xlabel("跟上  正式修改后改用新规范的比例", fontsize=11, color=SUB, labelpad=10); ax.set_ylabel("守住  个人违背后仍按团队规范做的比例", fontsize=11, color=SUB, labelpad=10)
ax.tick_params(length=0, pad=6)
for s in ax.spines.values(): s.set_visible(False)
fig.text(0.04, 0.95, "没有一个记忆系统两边都做对", fontsize=14, color=INK, va="center")
fig.savefig(f"{OUT}/fig3_跟上与守住.png", dpi=200); plt.close(fig)
print("ok")
