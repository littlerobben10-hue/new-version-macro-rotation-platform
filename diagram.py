"""
Blue Eagle Decision Flow Diagram
Mirrors the Q-Learning trading diagram concept,
adapted to the actual Blue Eagle signal engine code.
"""

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch
import numpy as np

# ── canvas ──────────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(18, 9))
fig.patch.set_facecolor("#0d1117")

# Two side-by-side sub-diagrams
ax1 = fig.add_axes([0.02, 0.05, 0.46, 0.90])   # Macro Market Model
ax2 = fig.add_axes([0.52, 0.05, 0.46, 0.90])   # Sector Rotation Model

for ax in (ax1, ax2):
    ax.set_facecolor("#0d1117")
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 10)
    ax.axis("off")


# ── helpers ──────────────────────────────────────────────────────────────────
def rounded_box(ax, x, y, w, h, fc, ec, lw=2, pad=0.15):
    box = FancyBboxPatch((x, y), w, h,
                         boxstyle=f"round,pad={pad}",
                         facecolor=fc, edgecolor=ec, linewidth=lw, zorder=3)
    ax.add_patch(box)
    return box


def arrow(ax, x0, y0, x1, y1, color="#888888", lw=1.8, rad=0.0):
    ax.annotate(
        "", xy=(x1, y1), xytext=(x0, y0),
        arrowprops=dict(
            arrowstyle="-|>", color=color, lw=lw,
            connectionstyle=f"arc3,rad={rad}",
        ),
        zorder=4,
    )


def circle(ax, cx, cy, r, fc, ec, lw=2):
    c = Circle((cx, cy), r, facecolor=fc, edgecolor=ec, linewidth=lw, zorder=3)
    ax.add_patch(c)


def txt(ax, x, y, s, color="#cccccc", size=9, ha="center", va="center",
        bold=False, italic=False):
    weight = "bold" if bold else "normal"
    style  = "italic" if italic else "normal"
    ax.text(x, y, s, color=color, fontsize=size, ha=ha, va=va,
            fontweight=weight, fontstyle=style, zorder=5)


# ═══════════════════════════════════════════════════════════════════════════════
# LEFT DIAGRAM — Macro Market Model  (mirrors Q-learning slide)
# ═══════════════════════════════════════════════════════════════════════════════
ax = ax1
ax.set_title("Macro Market Timing Model  ·  S&P 500 Signal Engine",
             color="white", fontsize=12, fontweight="bold", pad=8)

# ── mini faux-price-chart background ────────────────────────────────────────
np.random.seed(42)
xs = np.linspace(0, 10, 200)
price = np.cumsum(np.random.randn(200) * 0.04) + 3.5
ax.plot(xs, price, color="#1f4e79", linewidth=1.2, alpha=0.35, zorder=1)
ax.fill_between(xs, price.min() - 0.2, price, color="#1f4e79", alpha=0.07, zorder=1)

# ── "Now" label + vertical dashed line ──────────────────────────────────────
ax.axvline(x=3.1, ymin=0.25, ymax=0.95, color="#555", linestyle="--", linewidth=1, zorder=2)
txt(ax, 3.1, 9.3, "Now", color="#aaaaaa", size=9, italic=True)

# ── Features box  (X1, X2, X3, X4) ─────────────────────────────────────────
rounded_box(ax, 0.4, 0.8, 5.0, 2.2, "#0f1e2e", "#4a7fb5", lw=1.8)
txt(ax, 2.9, 2.7,  "Market State Features",     color="#4a7fb5", size=9,  bold=True)
txt(ax, 2.9, 2.35, "X₁ · ISM Manufacturing New Orders  →  vote (+1 / 0)",  color="#bbbbbb", size=8)
txt(ax, 2.9, 2.00, "X₂ · Real M2 Impulse (YoY 6-mo Δ) →  vote (+1 / −1)", color="#bbbbbb", size=8)
txt(ax, 2.9, 1.65, "X₃ · 10Y Treasury Rate Change       →  vote (+1 / −1)", color="#bbbbbb", size=8)
txt(ax, 2.9, 1.30, "X₄ · Price Momentum (14d / 180d)    →  Bullish / Bearish", color="#bbbbbb", size=8)

# ── Upward arrow  "s" ───────────────────────────────────────────────────────
arrow(ax, 2.9, 3.0, 2.9, 4.2, color="#888888", lw=2.0)
txt(ax, 3.3, 3.6, "s", color="#aaaaaa", size=13, italic=True, bold=True)

# ── Signal Engine box  Q[s, a] ──────────────────────────────────────────────
rounded_box(ax, 0.4, 4.2, 5.0, 2.2, "#111e2e", "#f5c518", lw=2.2)
txt(ax, 2.9, 6.1,  "Signal Engine",                  color="#f5c518", size=10, bold=True)
txt(ax, 2.9, 5.75, "Score [s, action]",               color="white",  size=12, bold=True, italic=True)
txt(ax, 2.9, 5.40, "Macro Score = ISM + M2 + Rate votes  ∈ {−3 … 3}", color="#aaaaaa", size=8)
txt(ax, 2.9, 5.05, "BUY  if  score ≥ 2",              color="#2ca02c", size=8)
txt(ax, 2.9, 4.72, "SELL if  score ≤ −1  AND  Momentum Bearish",       color="#d62728", size=8)
txt(ax, 2.9, 4.40, "HOLD otherwise",                  color="#f5c518", size=8)

# ── Horizontal arrow  → Action ──────────────────────────────────────────────
arrow(ax, 5.4, 5.3, 6.6, 5.3, color="#aaaaaa", lw=2.2)

# ── Action box ──────────────────────────────────────────────────────────────
rounded_box(ax, 6.6, 4.55, 2.9, 1.5, "#1b4332", "#2ca02c", lw=2.2)
txt(ax, 8.05, 5.6,  "🟢 Action: BUY",  color="#2ca02c", size=11, bold=True)
txt(ax, 8.05, 5.15, "Go long S&P 500", color="#aaaaaa", size=8)
txt(ax, 8.05, 4.82, "(or SELL = flat)", color="#888888", size=7.5)

# ── Reward circle ────────────────────────────────────────────────────────────
circle(ax, 8.0, 2.6, 1.1, "#2b1a00", "#f5c518", lw=2.2)
txt(ax, 8.0, 2.9,  "Reward:",          color="#f5c518", size=9,  bold=True)
txt(ax, 8.0, 2.55, "Monthly S&P",      color="#f5c518", size=8.5)
txt(ax, 8.0, 2.22, "Return",           color="#f5c518", size=8.5)

# ── Arrow  Action → Reward ──────────────────────────────────────────────────
arrow(ax, 8.0, 4.55, 8.0, 3.7, color="#f5c518", lw=1.8)

# ── "Update Q" feedback arc ─────────────────────────────────────────────────
txt(ax, 5.2, 8.5, "Update Signals", color="#f5c518", size=10, bold=True)
ax.annotate(
    "", xy=(2.9, 6.4), xytext=(7.0, 3.7),
    arrowprops=dict(arrowstyle="-|>", color="#f5c518", lw=1.8,
                    connectionstyle="arc3,rad=-0.38"),
    zorder=4,
)


# ═══════════════════════════════════════════════════════════════════════════════
# RIGHT DIAGRAM — Sector Rotation Model
# ═══════════════════════════════════════════════════════════════════════════════
ax = ax2
ax.set_title("Sector Rotation Model  ·  GICS Sector Signal Engine",
             color="white", fontsize=12, fontweight="bold", pad=8)

# ── mini faux-sector bars background ────────────────────────────────────────
np.random.seed(7)
bx = np.arange(11)
heights = np.random.randn(11) * 0.3 + 3.2
colors_bg = ["#1b4332" if h > 3.2 else "#3b0d0c" if h < 3.0 else "#33291a"
             for h in heights]
ax.bar(bx * 0.9 + 0.5, heights - 2.8, bottom=2.8, width=0.7,
       color=colors_bg, alpha=0.25, zorder=1)

# ── "Now (month-end)" ───────────────────────────────────────────────────────
ax.axvline(x=3.1, ymin=0.25, ymax=0.95, color="#555", linestyle="--", linewidth=1, zorder=2)
txt(ax, 3.1, 9.3, "Now  (month-end)", color="#aaaaaa", size=9, italic=True)

# ── Features box ────────────────────────────────────────────────────────────
rounded_box(ax, 0.4, 0.8, 5.0, 2.2, "#0f1e2e", "#4a7fb5", lw=1.8)
txt(ax, 2.9, 2.7,  "Sector-Level Features",          color="#4a7fb5", size=9,  bold=True)
txt(ax, 2.9, 2.35, "X₁ · Sector Momentum Raw  (lookback compound return)",   color="#bbbbbb", size=8)
txt(ax, 2.9, 2.00, "X₂ · Momentum Z-score      (cross-sectional normalised)", color="#bbbbbb", size=8)
txt(ax, 2.9, 1.65, "X₃ · Macro Regime Adj.     (+0.25 Cyclical/Expansion,",  color="#bbbbbb", size=8)
txt(ax, 2.9, 1.30, "                             +0.25 Defensive/Contraction)", color="#666666", size=7.5)

# ── Upward arrow ─────────────────────────────────────────────────────────────
arrow(ax, 2.9, 3.0, 2.9, 4.2, color="#888888", lw=2.0)
txt(ax, 3.3, 3.6, "s", color="#aaaaaa", size=13, italic=True, bold=True)

# ── Signal Engine box ────────────────────────────────────────────────────────
rounded_box(ax, 0.4, 4.2, 5.0, 2.2, "#111e2e", "#f5c518", lw=2.2)
txt(ax, 2.9, 6.1,  "Signal Engine",                          color="#f5c518", size=10, bold=True)
txt(ax, 2.9, 5.75, "Rank [sector, score]",                   color="white",  size=12, bold=True, italic=True)
txt(ax, 2.9, 5.40, "Final Score = Z-score + Macro Adjustment", color="#aaaaaa", size=8)
txt(ax, 2.9, 5.05, "GREEN  (Top N sectors  → Long)",         color="#2ca02c", size=8)
txt(ax, 2.9, 4.72, "RED      (Bottom N sectors → Short)",     color="#d62728", size=8)
txt(ax, 2.9, 4.40, "YELLOW (Middle → Watch)",                color="#f5c518", size=8)

# ── Horizontal arrow → Action ────────────────────────────────────────────────
arrow(ax, 5.4, 5.3, 6.6, 5.3, color="#aaaaaa", lw=2.2)

# ── Action box ───────────────────────────────────────────────────────────────
rounded_box(ax, 6.6, 4.55, 2.9, 1.5, "#1b4332", "#2ca02c", lw=2.2)
txt(ax, 8.05, 5.6,  "🟢 Action: LONG",  color="#2ca02c", size=11, bold=True)
txt(ax, 8.05, 5.15, "Top-N Sectors",   color="#aaaaaa", size=8)
txt(ax, 8.05, 4.82, "(equal weight)",  color="#888888", size=7.5)

# ── Reward circle ─────────────────────────────────────────────────────────────
circle(ax, 8.0, 2.6, 1.1, "#2b1a00", "#f5c518", lw=2.2)
txt(ax, 8.0, 2.9,  "Reward:",          color="#f5c518", size=9,  bold=True)
txt(ax, 8.0, 2.55, "Fwd 1-Mo",         color="#f5c518", size=8.5)
txt(ax, 8.0, 2.22, "Sector Return",    color="#f5c518", size=8.5)

# ── Arrow  Action → Reward ───────────────────────────────────────────────────
arrow(ax, 8.0, 4.55, 8.0, 3.7, color="#f5c518", lw=1.8)

# ── "Update Q" feedback arc ──────────────────────────────────────────────────
txt(ax, 5.2, 8.5, "Update Rankings", color="#f5c518", size=10, bold=True)
ax.annotate(
    "", xy=(2.9, 6.4), xytext=(7.0, 3.7),
    arrowprops=dict(arrowstyle="-|>", color="#f5c518", lw=1.8,
                    connectionstyle="arc3,rad=-0.38"),
    zorder=4,
)

# ── footer ────────────────────────────────────────────────────────────────────
fig.text(0.5, 0.01,
         "Blue Eagle Sector Rotation Platform  ·  Momentum × Macro × GICS  ·  "
         "WRDS · CRSP · Compustat · FRED",
         ha="center", color="#555555", fontsize=8)

# ── divider line between panels ──────────────────────────────────────────────
fig.add_artist(
    plt.Line2D([0.495, 0.495], [0.05, 0.97],
               transform=fig.transFigure, color="#333333", lw=1.2)
)

plt.savefig("blue_eagle_diagram.png", dpi=160, bbox_inches="tight",
            facecolor=fig.get_facecolor())
print("Saved: blue_eagle_diagram.png")
plt.show()
