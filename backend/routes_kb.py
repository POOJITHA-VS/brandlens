"""Knowledge base: clauses, facts, glossary, brand voice, guideline import."""
import re, json, time, io, base64, hashlib, hmac
from datetime import date, timedelta
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
from database import db, H
from auth import auth, log, tok
from engine import analyze, voice, conflicts

router = APIRouter()

KEYS = {"clauses": ("id", ("id", "sec", "text")), "facts": ("id", ("id", "key", "text", "value", "owner", "expiry")), "gloss": ("bad", ("bad", "good"))}

@router.get("/api/kb")
async def kb(req: Request):
    auth(req); return {"clauses": db("SELECT * FROM clauses"), "facts": db("SELECT * FROM facts"), "gloss": db("SELECT * FROM gloss"), "voice": db("SELECT v FROM settings WHERE k='voice'", one=True)["v"], "conflicts": conflicts()}
@router.post("/api/kb/{t}")
async def kb_add(t: str, req: Request):
    u = auth(req, "Admin"); b = await req.json()
    if t not in KEYS or not all(b.get(c) for c in KEYS[t][1] if c != "owner"): raise HTTPException(400, "Fill in every field")
    cols = KEYS[t][1]; db(f"INSERT OR REPLACE INTO {t}({','.join(cols)}) VALUES({','.join('?' * len(cols))})", [b.get(c, "Admin") for c in cols]); log(u, f"Saved {t} entry {b[cols[0]]}"); return {"ok": 1}
@router.delete("/api/kb/{t}/{k}")
async def kb_del(t: str, k: str, req: Request):
    u = auth(req, "Admin")
    if t not in KEYS: raise HTTPException(400, "Bad type")
    db(f"DELETE FROM {t} WHERE {KEYS[t][0]}=?", (k,)); log(u, f"Deleted {t} entry {k}"); return {"ok": 1}
@router.post("/api/voice")
async def set_voice(req: Request):
    u = auth(req, "Admin"); b = await req.json(); db("INSERT OR REPLACE INTO settings VALUES('voice',?)", (b.get("text", ""),)); log(u, "Updated brand voice sample"); return {"ok": 1}
@router.post("/api/import")  # guideline file -> clause records
async def imp(req: Request):
    u = auth(req, "Admin"); b = await req.json(); raw = base64.b64decode(b["b64"]); name = b["name"].lower()
    try:
        if name.endswith(".pdf"):
            import pdfplumber; text = "\n".join((p.extract_text() or "") for p in pdfplumber.open(io.BytesIO(raw)).pages)
        elif name.endswith(".docx"):
            import docx; text = "\n".join(p.text for p in docx.Document(io.BytesIO(raw)).paragraphs)
        else: text = raw.decode("utf-8", "ignore")
    except ImportError: raise HTTPException(400, "Install pdfplumber / python-docx for PDF/DOCX, or upload .txt/.md")
    sec, n = "General", (db("SELECT COUNT(*) c FROM clauses WHERE id LIKE 'G-%'", one=True)["c"])
    for line in [l.strip(" -•*#\t") for l in text.splitlines() if l.strip()]:
        if len(line.split()) <= 5 and not line.endswith("."): sec = line[:40]; continue
        for s in re.split(r"(?<=[.!?])\s+", line):
            if len(s) > 20: n += 1; db("INSERT OR REPLACE INTO clauses VALUES(?,?,?)", (f"G-{n}", sec, s))
    log(u, f"Imported guideline file {b['name']} ({n} clauses total G-*)"); return {"ok": 1}

