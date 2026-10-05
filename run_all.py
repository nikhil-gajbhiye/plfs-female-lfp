"""Replicate headline PLFS indicators, decompose female LFPR change, and draw the charts."""
import json, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from src.plfs import ROUNDS, load, rate

INK, TEAL, GOLD, GREY, RED = "#1d2b4f", "#1b8a8a", "#d9a21b", "#8a94a6", "#b23a48"
plt.rcParams.update({"font.family": "DejaVu Sans", "axes.spines.top": False, "axes.spines.right": False,
                     "axes.edgecolor": GREY, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
                     "font.size": 11, "figure.dpi": 150})
data = {k: load(k) for k in ROUNDS}

# ---- 1. headline indicators -------------------------------------------------------------
rows = []
for k, d in data.items():
    f = d[d.sex == 2]
    lf, wp = rate(d, "lf"), rate(d, "emp")
    rows.append(dict(round=k, lfpr=lf, wpr=wp, ur=100 * (1 - wp / lf), lfpr_male=rate(d[d.sex == 1], "lf"),
                     lfpr_female=rate(f, "lf"), lfpr_f_rural=rate(f[f.sec == 1], "lf"), lfpr_f_urban=rate(f[f.sec == 2], "lf"),
                     lfpr_female_excl_suspect=rate(f[~f.suspect], "lf"), n_suspect=int(d.suspect.sum())))
head = pd.DataFrame(rows).round(2); head.to_csv("results/headline_indicators.csv", index=False)

# ---- 2. what kind of work are women doing? (share of ALL women 15+) --------------------------
cats = ["Own-account / employer", "Unpaid helper", "Regular wage/salary", "Casual labour"]
comp = {}
for k, d in data.items():
    f = d[d.sex == 2]; r = {c: 100 * f.w[f.status == c].sum() / f.w.sum() for c in cats}
    r["Unemployed"] = rate(f, "unemp"); r["Out of labour force"] = 100 - rate(f, "lf"); comp[k] = r
comp = pd.DataFrame(comp).T.round(2); comp.to_csv("results/female_status_composition.csv")
fr = {k: {c: 100 * d.w[(d.sex == 2) & (d.sec == 1) & (d.status == c)].sum() / d.w[(d.sex == 2) & (d.sec == 1)].sum() for c in cats} for k, d in data.items()}
pd.DataFrame(fr).T.round(2).to_csv("results/female_status_composition_rural.csv")

# ---- 3. Kitagawa decomposition of the change in female LFPR ---------------------------------
def cells(d):
    f = d[d.sex == 2].copy()
    f["ag"] = pd.cut(f.age, [14, 24, 34, 44, 59, 200], labels=False)
    f["eg"] = pd.cut(f.edu, [0, 5, 7, 10, 13], labels=False)
    f["mg"] = (f.mar == 2).astype(int)
    g = f.groupby(["sec", "ag", "eg", "mg"], observed=True)
    out = pd.DataFrame({"pop": g.w.sum(), "lf": g.apply(lambda x: (x.lf * x.w).sum(), include_groups=False)})
    out["share"] = out["pop"] / out["pop"].sum(); out["rate"] = 100 * out.lf / out["pop"]
    return out

def kitagawa(a, b):
    c0, c1 = cells(data[a]), cells(data[b]); j = c0.join(c1, how="outer", lsuffix="0", rsuffix="1").fillna({"share0": 0, "share1": 0})
    j["rate0"] = j.rate0.fillna(j.rate1); j["rate1"] = j.rate1.fillna(j.rate0)
    comp_e = ((j.share1 - j.share0) * (j.rate0 + j.rate1) / 2).sum()
    rate_e = ((j.rate1 - j.rate0) * (j.share0 + j.share1) / 2).sum()
    tot = rate(data[b][data[b].sex == 2], "lf") - rate(data[a][data[a].sex == 2], "lf")
    return dict(total=tot, composition=comp_e, within_group=rate_e, check=comp_e + rate_e - tot)

dec = {"2017-18 to 2023-24": kitagawa("2017-18", "2023-24"), "2023-24 to CY2025 (crosses redesign)": kitagawa("2023-24", "CY2025")}
json.dump({"decomposition": dec, "headline": head.to_dict("records")}, open("results/results.json", "w"), indent=1)

# ---- 4. charts ----------------------------------------------------------------------------------
x = np.arange(len(head)); lab = [r.replace("CY", "CY ") for r in head["round"]]
fig, ax = plt.subplots(figsize=(8.4, 4.6))
for col, c, t in [("lfpr_f_rural", TEAL, "Rural women"), ("lfpr_female", INK, "All women"), ("lfpr_f_urban", GOLD, "Urban women")]:
    ax.plot(x, head[col], color=c, lw=2.4, marker="o", ms=4); ax.text(x[-1] + .15, head[col].iloc[-1], f"{t} {head[col].iloc[-1]:.0f}%", color=c, va="center", fontsize=10)
ax.axvline(6.5, color=GREY, ls=":", lw=1); ax.axvline(7.5, color=RED, ls=":", lw=1)
ax.text(6.55, 55, "July-June rounds\nend; calendar\nyears begin", fontsize=8, color=GREY, va="top"); ax.text(7.55, 55, "2025 sample\nredesign", fontsize=8, color=RED, va="top")
ax.set_xticks(x); ax.set_xticklabels(lab, rotation=35, ha="right", fontsize=9); ax.set_ylim(15, 58); ax.set_xlim(-.3, 11.3)
ax.set_ylabel("LFPR, age 15+, usual status (ps+ss), %"); ax.set_title("Women's labour force participation, 2017-18 to 2025", loc="left", color=INK, fontweight="bold", fontsize=12)
fig.tight_layout(); fig.savefig("docs/img/female_lfpr_trend.svg", bbox_inches="tight"); plt.close(fig)

pick = ["2017-18", "2023-24", "CY2025"]; colors = [INK, TEAL, GOLD, "#c9ced8", RED, "#eef0f4"]
fig, ax = plt.subplots(figsize=(8.4, 3.6)); left = np.zeros(3)
for c, col in zip(list(comp.columns), colors):
    v = comp.loc[pick, c].values; ax.barh(range(3), v, left=left, color=col, height=.58, label=c)
    for i, (l, w_) in enumerate(zip(left, v)):
        if w_ > 4: ax.text(l + w_ / 2, i, f"{w_:.0f}", ha="center", va="center", color="white" if col in (INK, TEAL, RED) else INK, fontsize=9)
    left += v
ax.set_yticks(range(3)); ax.set_yticklabels([p.replace("CY", "CY ") for p in pick]); ax.invert_yaxis(); ax.set_xlim(0, 100); ax.set_xlabel("% of women aged 15+")
ax.legend(ncol=3, fontsize=8, frameon=False, loc="upper center", bbox_to_anchor=(.5, -.28)); ax.set_title("What women are doing", loc="left", color=INK, fontweight="bold", fontsize=12)
fig.tight_layout(); fig.savefig("docs/img/female_status_composition.svg", bbox_inches="tight"); plt.close(fig)

d1 = dec["2017-18 to 2023-24"]; fig, ax = plt.subplots(figsize=(8.4, 2.6))
ax.barh([1, 0], [d1["composition"], d1["within_group"]], color=[GREY, TEAL], height=.55)
for y, v in zip([1, 0], [d1["composition"], d1["within_group"]]): ax.text(v + .3, y, f"{v:+.1f} pp", va="center", color=INK, fontsize=10)
ax.set_yticks([1, 0]); ax.set_yticklabels(["Who women are\n(age, education, marital status, sector)", "Participation within\nthe same kinds of women"], fontsize=9)
ax.set_xlim(0, max(d1["composition"], d1["within_group"]) + 4); ax.set_xlabel(f"Percentage-point change in female LFPR, 2017-18 to 2023-24 (total {d1['total']:+.1f} pp)")
ax.set_title("Where the rise comes from", loc="left", color=INK, fontweight="bold", fontsize=12); fig.tight_layout(); fig.savefig("docs/img/decomposition.svg", bbox_inches="tight"); plt.close(fig)
print(head.to_string(index=False)); print(); print(comp.to_string()); print(); print(json.dumps(dec, indent=1))
