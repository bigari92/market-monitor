import json, re, os, hashlib
SRC = r"C:\Users\valer\.claude\projects\C--Users-valer-Investing\a65146b1-c1e6-4733-aea1-2152de4aaabb.jsonl"
OUT = r"C:\Users\valer\AppData\Local\Temp\claude\C--Users-valer-OneDrive--------------Claude\36d82577-aa1d-4ab0-9237-5a5865d2bc0c\scratchpad\recovered"
os.makedirs(OUT, exist_ok=True)
bash=[]
for line in open(SRC, encoding="utf-8"):
    try: o=json.loads(line)
    except: continue
    m=o.get("message")
    if not isinstance(m,dict): continue
    c=m.get("content")
    if not isinstance(c,list): continue
    for b in c:
        if isinstance(b,dict) and b.get("type")=="tool_use" and b.get("name")=="Bash":
            bash.append((b.get("input") or {}).get("command","") or "")
# heredoc pattern: cat > NAME << 'TAG' ... TAG
pat = re.compile(r"cat\s*>\s*([^\s;|>]+\.py)\s*<<\s*['\"]?(\w+)['\"]?\s*\n(.*?)\n\2\s*(?:\n|$)", re.S)
found={}
order=[]
for i,cmd in enumerate(bash):
    for m2 in pat.finditer(cmd):
        name=os.path.basename(m2.group(1)); body=m2.group(3)
        found.setdefault(name,[]).append((i,body))
        order.append((i,name,len(body)))
print("distinct scripts recovered:", len(found))
tot=0
for name,vers in found.items():
    i,body = vers[-1]
    tot+=len(body)
    open(os.path.join(OUT,name),"w",encoding="utf-8").write(body+"\n")
print("total bytes:", tot)
# syntax-check each
import py_compile, traceback
ok=bad=0
for name in sorted(found):
    fp=os.path.join(OUT,name)
    try:
        py_compile.compile(fp, doraise=True, cfile=os.path.join(OUT,"__pyc_tmp"))
        ok+=1
    except Exception as e:
        bad+=1; print("  SYNTAX FAIL", name, type(e).__name__, str(e)[:120])
print(f"syntax OK: {ok}  FAIL: {bad}")
print("order of creation:")
for i,name,L in order: print(f"   cmd#{i:>3} {name:<28} {L:>6} bytes")
