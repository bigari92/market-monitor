# -*- coding: utf-8 -*-
"""Second pass on the report: renumber exhibits, rewrite the algorithm spec to v4,
refresh the validation numbers and chart, and replace the current screen output."""
h = open("report.html", encoding="utf-8").read()
n0 = len(h)

# ---------- 1. renumber: new fundamentals exhibit is 4, year-by-year becomes 5 ----------
h = h.replace('<span class="tag">Exhibit 5</span>\n      <span class="ttl">The same companies, sorted two ways</span>',
              '<span class="tag">Exhibit 4</span>\n      <span class="ttl">The same companies, sorted two ways</span>')
h = h.replace('<span class="tag">Exhibit 4</span>\n      <span class="ttl">Year by year',
              '<span class="tag">Exhibit 5</span>\n      <span class="ttl">Year by year')
h = h.replace('the expected distribution around it is the one in Exhibit 4',
              'the expected distribution around it is the one in Exhibit 5')

# ---------- 2. algorithm spec -> v4 ----------
old_spec_head = '''    <p>Four stages. Deliberately simple: weights are round numbers chosen from the sign and rough magnitude of each IC, not fitted. Optimising weights across 127 overlapping cross-sections would produce a better backtest and a worse forecast.</p>'''
new_spec_head = '''    <p>Four stages. Deliberately simple: weights are round numbers chosen from the sign and rough magnitude of each IC, not fitted. Optimising weights across 127 overlapping cross-sections would produce a better backtest and a worse forecast. Fundamentals were tested at this stage and left out &mdash; see Finding 08.</p>'''
assert old_spec_head in h
h = h.replace(old_spec_head, new_spec_head, 1)

old_step3 = '''        <div class="t">Quality-of-trend score</div>
        <div class="d">Cross-sectional z-scores, winsorised at &plusmn;3, combined with fixed weights. This is the loss-avoidance engine from Exhibit 2.</div>'''
new_step3 = '''        <div class="t">Quality-of-trend score</div>
        <div class="d">Cross-sectional <b>percentile ranks</b>, combined with fixed weights. This is the loss-avoidance engine from Exhibit 2. Ranks rather than z-scores: on skewed inputs the z-scored version let a few outliers set the ordering, and switching cost nothing and gained 3.9&nbsp;pp a year.</div>'''
assert old_step3 in h
h = h.replace(old_step3, new_step3, 1)

# ---------- 3. validation stat row ----------
old_stats = '''  <div class="stats">
    <div class="stat"><div class="v pos">+33.9%</div><div class="l">mean forward 12m<br><span class="mono">vs +14.6% universe</span></div></div>
    <div class="stat"><div class="v">+9.6%</div><div class="l">median forward 12m<br><span class="mono">vs &minus;5.1% universe</span></div></div>
    <div class="stat"><div class="v pos">29.6%</div><div class="l">hit a +50% year<br><span class="mono">1.27&times; the universe</span></div></div>
    <div class="stat"><div class="v neg">24.2%</div><div class="l">fell more than 30%<br><span class="mono">0.66&times; the universe</span></div></div>
  </div>'''
new_stats = '''  <div class="stats">
    <div class="stat"><div class="v pos">+37.8%</div><div class="l">mean forward 12m<br><span class="mono">vs +14.6% universe</span></div></div>
    <div class="stat"><div class="v">+15.4%</div><div class="l">median pick<br><span class="mono">vs &minus;5.1% universe</span></div></div>
    <div class="stat"><div class="v pos">30.7%</div><div class="l">hit a +50% year<br><span class="mono">1.32&times; the universe</span></div></div>
    <div class="stat"><div class="v neg">22.3%</div><div class="l">fell more than 30%<br><span class="mono">0.60&times; the universe</span></div></div>
  </div>'''
assert old_stats in h
h = h.replace(old_stats, new_stats, 1)

h = h.replace('<span class="sub">The algorithm beat its universe in 5 of 7 years. In 2021 it lost a third of its value.</span>',
              '<span class="sub">The algorithm beat its universe in 6 of 7 years. In 2021 it still lost a quarter of its value.</span>')

# ---------- 4. year-by-year chart, new numbers ----------
old_chart_start = h.index('<svg viewBox="0 0 760 336"')
old_chart_end = h.index('</svg>', old_chart_start) + len('</svg>')
new_chart = '''<svg viewBox="0 0 760 336" role="img" aria-label="Grouped bars by year comparing algorithm returns against universe returns, showing minus 24 percent in 2021">
        <line class="gl" x1="76" y1="40"  x2="726" y2="40"></line>
        <line class="gl" x1="76" y1="80"  x2="726" y2="80"></line>
        <line class="gl" x1="76" y1="120" x2="726" y2="120"></line>
        <line class="gl" x1="76" y1="160" x2="726" y2="160"></line>
        <line class="zl" x1="76" y1="200" x2="726" y2="200"></line>
        <line class="gl" x1="76" y1="240" x2="726" y2="240"></line>
        <line class="gl" x1="76" y1="280" x2="726" y2="280"></line>
        <text class="ax" x="68" y="44"  text-anchor="end">+80%</text>
        <text class="ax" x="68" y="84"  text-anchor="end">+60%</text>
        <text class="ax" x="68" y="124" text-anchor="end">+40%</text>
        <text class="ax" x="68" y="164" text-anchor="end">+20%</text>
        <text class="axb" x="68" y="204" text-anchor="end">0</text>
        <text class="ax" x="68" y="244" text-anchor="end">&minus;20%</text>
        <text class="ax" x="68" y="284" text-anchor="end">&minus;40%</text>

        <rect class="bn"   x="96"  y="96"  width="30" height="104"></rect>
        <rect class="bmut" x="128" y="161" width="30" height="39"></rect>
        <text class="ax" x="111" y="90" text-anchor="middle">+52</text>
        <text class="ax" x="127" y="306" text-anchor="middle">2019</text>

        <rect class="bn"   x="188" y="61"  width="30" height="139"></rect>
        <rect class="bmut" x="220" y="31"  width="30" height="169"></rect>
        <text class="ax" x="203" y="55" text-anchor="middle">+69</text>
        <text class="ax" x="235" y="25" text-anchor="middle">+84</text>
        <text class="ax" x="219" y="306" text-anchor="middle">2020</text>

        <rect class="bd"   x="280" y="200" width="30" height="48"></rect>
        <rect class="bmut" x="312" y="200" width="30" height="74"></rect>
        <text class="ax" x="295" y="263" text-anchor="middle" fill="var(--down)">&minus;24</text>
        <text class="axb" x="311" y="306" text-anchor="middle">2021</text>

        <rect class="bn"   x="372" y="198" width="30" height="2"></rect>
        <rect class="bmut" x="404" y="200" width="30" height="28"></rect>
        <text class="ax" x="387" y="192" text-anchor="middle">+1</text>
        <text class="ax" x="403" y="306" text-anchor="middle">2022</text>

        <rect class="bn"   x="464" y="111" width="30" height="89"></rect>
        <rect class="bmut" x="496" y="182" width="30" height="18"></rect>
        <text class="ax" x="479" y="105" text-anchor="middle">+44</text>
        <text class="ax" x="495" y="306" text-anchor="middle">2023</text>

        <rect class="bn"   x="556" y="81"  width="30" height="119"></rect>
        <rect class="bmut" x="588" y="183" width="30" height="17"></rect>
        <text class="ax" x="571" y="75" text-anchor="middle">+60</text>
        <text class="ax" x="587" y="306" text-anchor="middle">2024</text>

        <rect class="bn"   x="648" y="52"  width="30" height="148"></rect>
        <rect class="bmut" x="680" y="121" width="30" height="79"></rect>
        <text class="ax" x="663" y="46" text-anchor="middle">+74</text>
        <text class="ax" x="695" y="115" text-anchor="middle">+39</text>
        <text class="ax" x="679" y="306" text-anchor="middle">2025</text>

        <rect class="bn" x="300" y="322" width="12" height="10"></rect>
        <text class="ax" x="318" y="331">algorithm, top 25</text>
        <rect class="bmut" x="470" y="322" width="12" height="10"></rect>
        <text class="ax" x="488" y="331">gated universe</text>
      </svg>'''
h = h[:old_chart_start] + new_chart + h[old_chart_end:]

# ---------- 5. pick-distribution paragraph + 2021 caveat ----------
old_dist = '''    <p>The distribution of the 2,000 individual picks is what a user should actually plan around: 5th percentile <span class="mono">&minus;69%</span>, median <span class="mono">+10%</span>, 75th <span class="mono">+63%</span>, 95th <span class="mono">+226%</span>. Just <span class="mono">56%</span> were profitable. The mean is carried by the <span class="mono">17%</span> that doubled.</p>'''
new_dist = '''    <p>The distribution of the 2,000 individual picks is what to actually plan around: 5th percentile <span class="mono">&minus;67%</span>, median <span class="mono">+15%</span>, 75th <span class="mono">+66%</span>, 95th <span class="mono">+231%</span>. Only <span class="mono">60%</span> were profitable. The mean is carried by the <span class="mono">17%</span> that doubled.</p>'''
assert old_dist in h
h = h.replace(old_dist, new_dist, 1)

old_2021 = '''      Signals formed during 2021 lost <b>31%</b> over the following year, with <b>55%</b> of picks down more than 30%.'''
new_2021 = '''      Signals formed during 2021 lost <b>24%</b> over the following year, with <b>53%</b> of picks down more than 30%.'''
assert old_2021 in h
h = h.replace(old_2021, new_2021, 1)

open("report.html", "w", encoding="utf-8").write(h)
print("pass 2 done: %d -> %d chars" % (n0, len(h)))

