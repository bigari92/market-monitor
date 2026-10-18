# -*- coding: utf-8 -*-
"""Third pass: rebuild the current-output table from the real screen CSV, and update
the limitations section now that fundamentals have been tested."""
import pandas as pd, numpy as np

h = open("report.html", encoding="utf-8").read()
n0 = len(h)

full = pd.read_csv("out/screen_v4_full.csv", index_col=0)
n_uni = len(full)
n_fund = int(full["rule40"].notna().sum())
d = full.head(15)

SHORT = {
    "Biotechnology: Pharmaceutical Preparations": "Biotech &mdash; pharma",
    "Biotechnology: Biological Products (No Diagnostic Substances)": "Biotech &mdash; biologics",
    "Telecommunications Equipment": "Telecom equipment",
    "Electronic Components": "Electronic components",
    "Electrical Products": "Electrical products",
    "Integrated oil Companies": "Integrated oil",
    "Precious Metals": "Precious metals",
    "Semiconductors": "Semiconductors",
}

def fmt(v, pct=False, dp=2, plus=False):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return '<span style="color:var(--muted)">n/a</span>'
    if pct:
        s = "%+.0f%%" % (100 * v) if plus else "%.0f%%" % (100 * v)
        return s.replace("-", "&minus;")
    return ("%+.2f" % v if plus else "%.2f" % v).replace("-", "&minus;")

rows = []
for i, r in d.iterrows():
    ind = SHORT.get(r["industry"], str(r["industry"])[:26])
    m36 = r["mom_36"]
    m36s = ("+%.0f%%" % (100 * m36))
    m36cell = ('<td class="mono neg">%s</td>' % m36s) if m36 > 8.0 else ('<td class="mono">%s</td>' % m36s)
    r40 = r["rule40"]
    r40cell = '<td class="mono">%s</td>' % fmt(r40, pct=True, plus=True) if np.isfinite(r40) else '<td class="mono" style="color:var(--muted)">n/a</td>'
    rows.append(
        '        <tr><td class="mono">%d</td><td class="mono"><b>%s</b></td><td>%s</td>'
        '<td class="mono">%.2f</td><td class="mono">%s</td><td class="mono">%s</td>'
        '%s%s<td class="mono">%s</td></tr>'
        % (i, r["ticker"], ind, r["final_score"],
           fmt(r["pct_of_52w_high"], pct=True),
           fmt(r["max_dd_12m"], pct=True, plus=True),
           m36cell, r40cell,
           fmt(r["rev_yoy_ttm"], pct=True, plus=True)))

table = (
'''  <div class="tbl-wrap">
    <table>
      <thead>
        <tr><th>#</th><th>Ticker</th><th>Industry</th><th>Score</th><th>% of 52w high</th><th>Max DD</th><th>3y mom</th><th>Rule of 40</th><th>Rev growth</th></tr>
      </thead>
      <tbody>
''' + "\n".join(rows) + '''
      </tbody>
    </table>
  </div>''')

start = h.index('  <div class="tbl-wrap">', h.index('<h2>What the screen returns today</h2>'))
end = h.index('</div>', h.index('</table>', start)) + len('</div>')
h = h[:start] + table + h[end:]

old_lead = ('Run on data through 4 September 2026. 529 names cleared the liquidity and volatility gates; '
            'these are the top 15 by final score. <b>This is the algorithm&rsquo;s output, not a recommendation</b> '
            '&mdash; the expected distribution around it is the one in Exhibit 5, where a quarter of picks fall more than 30%.')
new_lead = ('Run on data through 4 September 2026 with the validated rank-normalised score. %d names cleared the '
            'liquidity and volatility gates, %d of them with current SEC fundamentals; these are the top 15. '
            'Rule of 40 and revenue growth are shown as <em>context only</em> &mdash; they are not scored. '
            '<b>This is the algorithm&rsquo;s output, not a recommendation</b> &mdash; the expected distribution around '
            'it is the one in Exhibit 5, where 22%% of picks fall more than 30%%.') % (n_uni, n_fund)
assert old_lead in h, "lead paragraph not found"
h = h.replace(old_lead, new_lead, 1)

old_after = h[h.index('<p>Six of the top fifteen are semiconductors'):]
old_after_end = old_after.index('</p>') + 4
old_para = old_after[:old_after_end]
top = full.head(25)
n_semi = int((top["industry"] == "Semiconductors").sum())
n_bio = int(top["industry"].astype(str).str.startswith("Biotech").sum())
n_danger = int((top["mom_36"] > 8.0).sum())
new_para = (
    '<p>Of the top 25, %d are semiconductors and %d are biotech &mdash; read that as a <b>concentration warning</b>, '
    'not a confirmation: the screen has no diversification constraint and loads on the trade that has already run. '
    '%d names still carry 3-year gains inside the danger zone of Exhibit 3 (flagged in red); the over-extension '
    'penalty pushed them down the list rather than removing them.</p>' % (n_semi, n_bio, n_danger))
h = h.replace(old_para, new_para, 1)

old_lim = ('      <li><b>Price and volume only.</b> No revenue growth, margins, valuation or earnings revisions. '
           'Free fundamental history is too thin for point-in-time testing without lookahead, so nothing fundamental '
           'was claimed rather than claimed badly.</li>')
new_lim = (
'''      <li><b>Fundamentals tested and excluded, not ignored.</b> Point-in-time revenue and margins were built from
      SEC XBRL and tested (Findings 07&ndash;08). They predict returns on their own but did not improve this screen,
      so they are reported rather than scored. Valuation and earnings revisions remain untested.</li>
      <li><b>Two residual risks in the SEC data.</b> The frames API returns the figure that best fits each calendar
      period, which can reflect a later <em>restatement</em> rather than the number first published &mdash; a mild
      lookahead this design cannot fully remove. And the 90-day availability lag is measured, not observed
      per-filing: it covers 96% of genuine first filings, so roughly 1 in 25 rows is read slightly early.</li>
      <li><b>Fundamental coverage is 72%</b> of the panel and skews by sector &mdash; banks report no gross profit,
      and unprofitable companies are over-represented among the missing.</li>''')
assert old_lim in h, "limitation bullet not found"
h = h.replace(old_lim, new_lim, 1)

h = h.replace(
    'Data: Yahoo Finance daily adjusted prices via <span class="mono">yfinance</span>; sector and market-cap reference from the Nasdaq screener API; universe from the Nasdaq Trader symbol directory.',
    'Data: Yahoo Finance daily adjusted prices via <span class="mono">yfinance</span>; quarterly fundamentals from the SEC XBRL <span class="mono">frames</span> API with filing lags measured from <span class="mono">companyconcept</span>; sector and market-cap reference from the Nasdaq screener API; universe from the Nasdaq Trader symbol directory.')

open("report.html", "w", encoding="utf-8").write(h)
print("pass 3 done: %d -> %d chars | universe %d | with fundamentals %d | danger-zone names %d"
      % (n0, len(h), n_uni, n_fund, n_danger))

