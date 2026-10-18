"""Does the screen say anything at a 3-month horizon? It was built and validated on 12.

Recomputes forward returns at 63 trading days (~3 months) on the same rebalance dates
and re-runs the same tests: base rates, score IC, and top-25 selection performance.
"""
import numpy as np, pandas as pd
from scipy import stats
import factors as F, algo_v4 as A4

H3, H12 = 63, 252

close, vol = F.load_panel()
p = pd.read_parquet("data/panel_fund90.parquet"); p["date"] = pd.to_datetime(p["date"])
idx = close.index

# forward return at 63 trading days for every (date, ticker) in the panel
fr = {}
for d in sorted(p["date"].unique()):
    pos = idx.searchsorted(pd.Timestamp(d), side="right") - 1
    f = pos + H3
    if pos < 0 or f >= len(idx):
        continue
    fr[d] = (close.iloc[f] / close.iloc[pos] - 1.0)
rows = []
for d, s in fr.items():
    rows.append(pd.DataFrame({"date": d, "ticker": s.index, "fwd3m": s.values}))
f3 = pd.concat(rows, ignore_index=True)
p = p.merge(f3, on=["date", "ticker"], how="left")
p = p[p.fwd3m.notna()]
print("panel with 3m forward returns: %d rows, %d dates" % (len(p), p.date.nunique()), flush=True)

print("", flush=True)
print("=== 1. BASE RATE OF A +50%% MOVE ===", flush=True)
p["vp"] = p.groupby("date")["vol_12m"].rank(pct=True)
hi = p[p.vp >= 0.80]
for nm, s in [("whole investable universe", p), ("top-20%% volatility cohort", hi)]:
    print("  %-28s  3 months: %5.2f%%   12 months: %5.2f%%" % (
        nm, 100*(s.fwd3m > 0.5).mean(), 100*(s.fwd_ret > 0.5).mean()), flush=True)

print("", flush=True)
print("=== 2. DOES THE SCORE PREDICT AT 3 MONTHS? (rank IC, high-vol cohort) ===", flush=True)
sc = []
for d, g in p.groupby("date"):
    s = A4.score(g, (0.80, 1.00), "price")
    if s is None or len(s) < 40:
        continue
    s = s.copy()
    sc.append(s[["date", "ticker", "score", "fwd3m", "fwd_ret"]])
S = pd.concat(sc, ignore_index=True)
for lab, col in [("3-month", "fwd3m"), ("12-month", "fwd_ret")]:
    ics = S.groupby("date").apply(
        lambda g: stats.spearmanr(g["score"], g[col])[0] if len(g) > 40 else np.nan,
        include_groups=False).dropna()
    print("  %-9s horizon:  mean IC %+.4f   t %+5.2f   months positive %4.1f%%   n %d" % (
        lab, ics.mean(), ics.mean()/(ics.std()/np.sqrt(len(ics))), 100*(ics>0).mean(), len(ics)), flush=True)

print("", flush=True)
print("=== 3. TOP-25 SELECTION, 3 MONTHS vs 12 MONTHS ===", flush=True)
oos = S[S.date >= "2019-01-01"]
rows = []
for d, g in oos.groupby("date"):
    t = g.sort_values("score", ascending=False).head(25)
    rows.append({"date": d,
                 "t3_mean": t.fwd3m.mean(), "t3_med": t.fwd3m.median(),
                 "t3_up50": (t.fwd3m > .5).mean(), "t3_dn30": (t.fwd3m < -.3).mean(),
                 "u3_up50": (g.fwd3m > .5).mean(),
                 "t12_mean": t.fwd_ret.mean(), "t12_up50": (t.fwd_ret > .5).mean()})
r = pd.DataFrame(rows)
print("  top-25 mean return      3m %+6.2f%%      12m %+6.2f%%" % (100*r.t3_mean.mean(), 100*r.t12_mean.mean()), flush=True)
print("  top-25 median return    3m %+6.2f%%" % (100*r.t3_med.mean()), flush=True)
print("  top-25 P(+50%%)          3m %6.2f%%      12m %6.2f%%" % (100*r.t3_up50.mean(), 100*r.t12_up50.mean()), flush=True)
print("  cohort P(+50%%)          3m %6.2f%%" % (100*r.u3_up50.mean()), flush=True)
print("  lift over cohort        3m %6.2fx" % (r.t3_up50.mean()/r.u3_up50.mean()), flush=True)
print("  top-25 P(-30%%)          3m %6.2f%%" % (100*r.t3_dn30.mean()), flush=True)

print("", flush=True)
print("=== 4. HOW OFTEN DOES *ANY* NAME DO IT? ===", flush=True)
n_any = p.groupby("date").apply(lambda g: (g.fwd3m > .5).sum(), include_groups=False)
n_tot = p.groupby("date").size()
print("  across the whole universe, per 3-month window:", flush=True)
print("    median %.0f names out of %.0f manage +50%%" % (n_any.median(), n_tot.median()), flush=True)
print("    worst window %d names, best window %d names" % (n_any.min(), n_any.max()), flush=True)
print("HORIZON_COMPLETE", flush=True)
