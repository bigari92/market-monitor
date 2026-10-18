"""Build a broad US-listed equity universe from NASDAQ Trader's official symbol directory."""
import io, sys
import pandas as pd
import urllib.request

HDRS = {"User-Agent": "Mozilla/5.0 (research script)"}

def fetch(url):
    req = urllib.request.Request(url, headers=HDRS)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")

def main():
    frames = []
    # NASDAQ-listed
    txt = fetch("https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt")
    df = pd.read_csv(io.StringIO(txt), sep="|")
    df = df[df["Symbol"].notna()]
    df = df[~df["Symbol"].astype(str).str.contains("File Creation Time", na=False)]
    df = df.rename(columns={"Security Name": "name"})
    df["exchange"] = "NASDAQ"
    df["etf"] = df.get("ETF", "N")
    df["test"] = df.get("Test Issue", "N")
    frames.append(df[["Symbol", "name", "exchange", "etf", "test"]])

    # NYSE / AMEX / other
    txt = fetch("https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt")
    df2 = pd.read_csv(io.StringIO(txt), sep="|")
    df2 = df2[df2["ACT Symbol"].notna()]
    df2 = df2[~df2["ACT Symbol"].astype(str).str.contains("File Creation Time", na=False)]
    df2 = df2.rename(columns={"ACT Symbol": "Symbol", "Security Name": "name", "Exchange": "exchange"})
    df2["etf"] = df2.get("ETF", "N")
    df2["test"] = df2.get("Test Issue", "N")
    frames.append(df2[["Symbol", "name", "exchange", "etf", "test"]])

    u = pd.concat(frames, ignore_index=True)
    u["Symbol"] = u["Symbol"].astype(str).str.strip()

    # Filter: drop ETFs, test issues, warrants/units/rights/preferreds, odd symbols
    u = u[u["etf"].astype(str).str.upper() != "Y"]
    u = u[u["test"].astype(str).str.upper() != "Y"]
    bad_name = r"(?i)\b(warrant|unit[s]?\b|right[s]?\b|depositary|preferred|% Notes|Trust Preferred|Subordinated)"
    u = u[~u["name"].astype(str).str.contains(bad_name, na=False, regex=True)]
    # Common stock symbols: 1-5 letters, no dots/dashes (drops class-B duplicates & preferreds)
    u = u[u["Symbol"].str.fullmatch(r"[A-Z]{1,5}")]
    u = u.drop_duplicates(subset="Symbol").sort_values("Symbol").reset_index(drop=True)

    u.to_csv("data/universe_raw.csv", index=False)
    print(f"universe size: {len(u)}")
    print(u["exchange"].value_counts().to_string())
    print(u.head(10).to_string())

if __name__ == "__main__":
    main()
