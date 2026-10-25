"""Fact-expiry alerts, what-if test, insights and audit log."""
import re, json, time, io, base64, hashlib, hmac
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from database import db, H
from auth import auth, log, tok
from engine import analyze, voice, conflicts

router = APIRouter()

from routes_subs import lastver

@router.get("/api/alerts")  # fact expiry alerts + drafts affected
async def alerts(req: Request):
    auth(req); lim = (date.today() + timedelta(days=30)).isoformat(); out = []
    for f in db("SELECT * FROM facts WHERE expiry<=?", (lim,)):
        aff = [s["title"] for s in db("SELECT id,title,status FROM subs WHERE status!='approved'") if any(x["ref"] == f["id"] for x in lastver(s["id"])["findings"])]
        out.append({**f, "expired": f["expiry"] < date.today().isoformat(), "affected": aff})
    return out
@router.post("/api/whatif")  # test a new banned term against past content before publishing the rule
async def whatif(req: Request):
    auth(req, "Admin", "Manager"); b = await req.json(); rx = re.compile(r"\b" + re.escape(b.get("bad", "")) + r"\b", re.I); hit = []
    for s in db("SELECT id,title FROM subs"):
        if b.get("bad") and rx.search(lastver(s["id"])["text"]): hit.append(s["title"])
    return {"affected": hit, "total": db("SELECT COUNT(*) c FROM subs", one=True)["c"]}
@router.get("/api/insights")
async def insights(req: Request):
    auth(req); cat, ref, team, tot = {}, {}, {}, {}; confs = {}
    for s in db("SELECT id,team FROM subs"):
        for v in db("SELECT findings FROM vers WHERE sub=?", (s["id"],)):
            for f in json.loads(v["findings"]):
                if f["status"] == "info": continue
                cat[f["cat"]] = cat.get(f["cat"], 0) + 1; team[s["team"]] = team.get(s["team"], 0) + 1
                r = ref.setdefault(f["ref"], {"n": 0, "d": 0, "c": 0}); r["n"] += 1; r["c"] += f["conf"]; r["d"] += f["status"] == "dismissed"
    clar = [{"ref": k, "n": r["n"], "dismissed": r["d"], "avg_conf": round(r["c"] / r["n"], 2)} for k, r in ref.items() if r["n"] >= 2 and (r["d"] / r["n"] >= .5 or r["c"] / r["n"] < .7)]
    fb = db("SELECT COUNT(*) c FROM fb", one=True)["c"]; tf = sum(r["n"] for r in ref.values())
    return {"cat": cat, "ref": {k: r["n"] for k, r in ref.items()}, "team": team, "clarity": clar, "conflicts": conflicts(), "wrong_flags": fb, "findings": tf, "precision": round(100 * (1 - fb / tf), 1) if tf else None}
@router.get("/api/audit")
async def audit(req: Request):
    auth(req); rows = db("SELECT * FROM audit ORDER BY id"); prev, ok = "0", True
    for r in rows:
        if r["prev"] != prev or r["hash"] != hashlib.sha256(f'{prev}|{r["ts"]}|{r["who"]}|{r["action"]}'.encode()).hexdigest(): ok = False
        prev = r["hash"]
    return {"ok": ok, "rows": rows[::-1][:200]}


@router.get("/api/stats")
async def stats(req: Request):
    u = auth(req); rows = []
    for s in db("SELECT id,title,channel,team,author,status,created FROM subs ORDER BY id DESC"):
        if u["r"] == "Creator" and s["author"] != u["n"]: continue
        v = lastver(s["id"]); o = [f for f in v["findings"] if f["status"] == "open"]
        s.update(n=v["n"], score=max(0, 100 - sum({"high": 15, "medium": 7, "low": 3}.get(f["sev"], 0) for f in o)), high=sum(f["sev"] == "high" for f in o), open=len(o)); rows.append(s)
    cnt = {k: sum(r["status"] == k for r in rows) for k in ("draft", "in_review", "changes", "approved")}
    act = db("SELECT ts,who,action FROM audit WHERE who LIKE ? ORDER BY id DESC LIMIT 7", (u["n"] + " (%" if u["r"] == "Creator" else "%",))
    return {"total": len(rows), **cnt, "avg": round(sum(r["score"] for r in rows) / len(rows)) if rows else None, "high": sum(r["high"] for r in rows), "all": rows[:200], "activity": act}
