"""Signed-token login, role checks and the hash-chained audit log."""
import json, base64, hmac, hashlib, time
from fastapi import HTTPException
from database import db
from config import SECRET

def tok(u):
    p = base64.urlsafe_b64encode(json.dumps({"n": u["name"], "r": u["role"], "t": u["team"], "f": u.get("full") or u["name"], "e": time.time() + 86400}).encode()).decode()
    return p + "." + hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()

def auth(req, *roles):
    h = req.headers.get("authorization", "")[7:]
    try:
        p, s = h.split(".")
        if not hmac.compare_digest(s, hmac.new(SECRET, p.encode(), hashlib.sha256).hexdigest()): raise ValueError
        u = json.loads(base64.urlsafe_b64decode(p))
        if u["e"] < time.time(): raise ValueError
    except Exception: raise HTTPException(401, "Please log in")
    if roles and u["r"] not in roles: raise HTTPException(403, "Your role cannot do this")
    return u

def log(u, a):
    last = db("SELECT hash FROM audit ORDER BY id DESC LIMIT 1", one=True); prev = last["hash"] if last else "0"
    ts = time.time(); who = f'{u["n"]} ({u["r"]})'
    db("INSERT INTO audit(ts,who,action,prev,hash) VALUES(?,?,?,?,?)", (ts, who, a, prev, hashlib.sha256(f"{prev}|{ts}|{who}|{a}".encode()).hexdigest()))

