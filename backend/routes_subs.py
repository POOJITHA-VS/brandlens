"""Submissions: versions, findings, comments, approval workflow, export."""
import re, json, time, io, base64, hashlib, hmac
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from database import db, H
from auth import auth, log, tok
from engine import analyze, voice, conflicts

router = APIRouter()

def getsub(sid, u):
    s = db("SELECT * FROM subs WHERE id=?", (sid,), one=True)
    if not s or (u["r"] == "Creator" and s["author"] != u["n"]): raise HTTPException(404, "Not found")
    s["meta"] = json.loads(s["meta"]); return s
def lastver(sid):
    v = db("SELECT * FROM vers WHERE sub=? ORDER BY n DESC LIMIT 1", (sid,), one=True); v["findings"] = json.loads(v["findings"]); return v
def mkver(s, text, meta):
    prev = db("SELECT findings FROM vers WHERE sub=? ORDER BY n DESC LIMIT 1", (s["id"],), one=True)
    F, ai = analyze(text, meta, s["channel"], s["purpose"])
    for o in (json.loads(prev["findings"]) if prev else []):
        if o["status"] == "dismissed":
            for f in F:
                if f["ref"] == o["ref"] and f["q"] == o["q"]: f["status"] = "dismissed"; f["why"] = o.get("why")
    n = (db("SELECT MAX(n) m FROM vers WHERE sub=?", (s["id"],), one=True)["m"] or 0) + 1
    db("INSERT INTO vers(sub,n,text,findings,voice,ai,ts) VALUES(?,?,?,?,?,?,?)", (s["id"], n, text, json.dumps(F), voice(text), ai, time.time()))
    db("UPDATE subs SET draft=?,meta=?,status='draft' WHERE id=?", (text, json.dumps(meta), s["id"])); return n


@router.post("/api/subs")
async def sub_new(req: Request):
    u = auth(req, "Creator"); b = await req.json()
    if not b.get("title") or not b.get("text", "").strip(): raise HTTPException(400, "Add a title and some content")
    meta = b.get("meta") or {"fg": "#000000", "bg": "#ffffff"}
    sid = db("INSERT INTO subs(title,channel,purpose,team,author,status,draft,meta,created) VALUES(?,?,?,?,?,?,?,?,?)", (b["title"], b.get("channel", "Blog"), b.get("purpose") or "(not stated)", u["t"], u["n"], "draft", b["text"], json.dumps(meta), time.time()))
    mkver(getsub(sid, u), b["text"], meta); log(u, f"Created submission #{sid} “{b['title']}”"); return {"id": sid}
@router.get("/api/subs")
async def subs(req: Request):
    u = auth(req); out = []
    for s in db("SELECT id,title,channel,team,author,status FROM subs ORDER BY id DESC"):
        if u["r"] == "Creator" and s["author"] != u["n"]: continue
        v = lastver(s["id"]); s.update(n=v["n"], open=sum(f["status"] == "open" for f in v["findings"])); out.append(s)
    return out
@router.get("/api/subs/{sid}")
async def sub_get(sid: int, req: Request):
    u = auth(req); s = getsub(sid, u); vs = db("SELECT * FROM vers WHERE sub=? ORDER BY n", (sid,))
    for v in vs: v["findings"] = json.loads(v["findings"])
    return {"sub": s, "vers": vs, "comments": db("SELECT * FROM comments WHERE sub=? ORDER BY id", (sid,))}
@router.put("/api/subs/{sid}/draft")
async def draft(sid: int, req: Request):
    u = auth(req, "Creator"); s = getsub(sid, u); b = await req.json()
    if s["status"] not in ("draft", "changes"): raise HTTPException(400, "Locked while in review or approved")
    db("UPDATE subs SET draft=?,meta=? WHERE id=?", (b["draft"], json.dumps(b["meta"]), sid)); return {"ok": 1}
@router.post("/api/subs/{sid}/version")
async def newver(sid: int, req: Request):
    u = auth(req, "Creator"); s = getsub(sid, u)
    if s["status"] not in ("draft", "changes"): raise HTTPException(400, "Locked while in review or approved")
    n = mkver(s, s["draft"], s["meta"]); log(u, f"Saved v{n} of #{sid}"); return {"n": n}
@router.post("/api/subs/{sid}/finding")
async def finding(sid: int, req: Request):
    u = auth(req); s = getsub(sid, u); b = await req.json(); v = lastver(sid); f = next((x for x in v["findings"] if x["id"] == b.get("fid")), None)
    if not f: raise HTTPException(404, "No such finding")
    a = b.get("action")
    if a in ("accept", "dismiss"):
        if u["r"] != "Creator" or s["status"] not in ("draft", "changes"): raise HTTPException(403, "Only the creator can do this, while drafting")
        if a == "accept":
            if not f["fix"]: raise HTTPException(400, "No fix to apply")
            shift = sum(len(x["fix"]) - len(x["q"]) for x in v["findings"] if x["status"] == "accepted" and 0 <= x["i"] < f["i"])
            k = f["i"] + shift
            if s["draft"][k:k + len(f["q"])] != f["q"]: k = s["draft"].find(f["q"])
            if k < 0: raise HTTPException(400, "Fix cannot be applied to the current draft")
            db("UPDATE subs SET draft=? WHERE id=?", (s["draft"][:k] + f["fix"] + s["draft"][k + len(f["q"]):], sid)); f["status"] = "accepted"
            for x in v["findings"]:  # other findings on the same words are resolved by this fix
                if x is not f and x["status"] == "open" and x["i"] >= 0 and x["i"] < f["i"] + len(f["q"]) and f["i"] < x["i"] + len(x["q"]):
                    x["status"] = "superseded"; x["why"] = "Resolved by the fix for " + f["ref"]
        else:
            if not b.get("reason", "").strip(): raise HTTPException(400, "Give a reason to dismiss")
            f["status"] = "dismissed"; f["why"] = b["reason"]
        log(u, f"{a.title()}ed {f['ref']} on #{sid}")
    elif a == "wrong":
        f["wrong"] = True; db("INSERT INTO fb VALUES(?,?,?,?)", (sid, v["n"], f["id"], f["ref"])); log(u, f"Marked {f['ref']} as wrong flag on #{sid}")
    else: raise HTTPException(400, "Bad action")
    db("UPDATE vers SET findings=? WHERE id=?", (json.dumps(v["findings"]), v["id"])); return {"ok": 1}
@router.post("/api/subs/{sid}/send")
async def send(sid: int, req: Request):
    u = auth(req, "Creator"); s = getsub(sid, u); v = lastver(sid)
    if s["status"] not in ("draft", "changes") or s["draft"] != v["text"]: raise HTTPException(400, "Save your edits as a new version first")
    db("UPDATE subs SET status='in_review' WHERE id=?", (sid,)); log(u, f"Sent #{sid} v{v['n']} for review"); return {"ok": 1}
@router.post("/api/subs/{sid}/decision")
async def decide(sid: int, req: Request):
    u = auth(req, "Manager", "Reviewer"); s = getsub(sid, u); b = await req.json(); v = lastver(sid)
    if s["status"] != "in_review": raise HTTPException(400, "Not in review")
    if b.get("d") == "approve":
        if u["r"] != "Reviewer": raise HTTPException(403, "Only a Reviewer can give final approval")
        if any(f["status"] == "open" and f["sev"] == "high" for f in v["findings"]): raise HTTPException(400, "High-severity findings are still open")
        db("UPDATE subs SET status='approved',appr=? WHERE id=?", (json.dumps({"n": v["n"], "by": u["n"], "ts": time.time(), "ai": v["ai"]}), sid)); log(u, f"Approved #{sid} v{v['n']}")
    else: db("UPDATE subs SET status='changes' WHERE id=?", (sid,)); log(u, f"Requested changes on #{sid}")
    return {"ok": 1}
@router.post("/api/subs/{sid}/comment")
async def comment(sid: int, req: Request):
    u = auth(req); s = getsub(sid, u); b = await req.json()
    if b.get("text", "").strip(): db("INSERT INTO comments(sub,n,who,text,ts) VALUES(?,?,?,?,?)", (sid, lastver(sid)["n"], f'{u["n"]} ({u["r"]})', b["text"], time.time())); log(u, f"Commented on #{sid}")
    return {"ok": 1}
@router.get("/api/subs/{sid}/export")
async def export(sid: int, req: Request):
    u = auth(req); s = getsub(sid, u)
    if s["status"] != "approved": raise HTTPException(400, "Only approved content can be exported")
    a = json.loads(s["appr"]); v = db("SELECT text FROM vers WHERE sub=? AND n=?", (sid, a["n"]), one=True)
    return PlainTextResponse(f'{v["text"]}\n\n---\nBrandLens approval stamp\nReviewed by: {a["by"]}\nVersion: v{a["n"]}\nApproved: {time.ctime(a["ts"])}\nAI disclosure: {a["ai"]}\n')

