"""Accounts: sign up (role and password chosen by the user), log in, session, password change, live check."""
import os, re, time
from fastapi import APIRouter, Request, HTTPException
from database import db, H, check
from auth import auth, log, tok
from engine import analyze

router = APIRouter()
FAILS = {}
ROLES = ("Creator", "Manager", "Reviewer", "Admin")

def pub(u): return {"token": tok(u), "name": u["name"], "full": u["full"] or u["name"], "role": u["role"], "team": u["team"]}
def strong(pw): return len(pw) >= 8 and re.search(r"[A-Za-z]", pw) and re.search(r"\d", pw)

@router.post("/api/register")
async def register(req: Request):
    b = await req.json(); name = b.get("name", "").strip().lower(); full = b.get("full", "").strip()[:40]
    pw = b.get("pw", ""); role = b.get("role"); team = (b.get("team") or "General").strip()[:30]
    if not re.fullmatch(r"[a-z0-9_]{3,20}", name): raise HTTPException(400, "Username: 3 to 20 letters, numbers or underscores")
    if len(full) < 2: raise HTTPException(400, "Enter your full name")
    if not strong(pw): raise HTTPException(400, "Password needs 8+ characters with a letter and a number")
    if role not in ROLES: raise HTTPException(400, "Choose a role")
    code = os.environ.get("BL_ADMIN_CODE")
    if role == "Admin" and code and b.get("code") != code: raise HTTPException(403, "Invalid admin code")
    if db("SELECT 1 FROM users WHERE name=?", (name,), one=True): raise HTTPException(409, "That username is taken")
    db("INSERT INTO users(name,full,role,team,pw,created) VALUES(?,?,?,?,?,?)", (name, full, role, team, H(pw), time.time()))
    log({"n": name, "r": role}, "Created account")
    return pub(db("SELECT * FROM users WHERE name=?", (name,), one=True))

@router.post("/api/login")
async def login(req: Request):
    b = await req.json(); n = b.get("name", "").strip().lower(); now = time.time()
    f = [t for t in FAILS.get(n, []) if now - t < 300]
    if len(f) >= 5: raise HTTPException(429, "Too many attempts. Try again in a few minutes")
    u = db("SELECT * FROM users WHERE name=?", (n,), one=True)
    if not u or not check(u["pw"], b.get("pw", "")):
        f.append(now); FAILS[n] = f; raise HTTPException(401, "Wrong username or password")
    FAILS.pop(n, None); log({"n": u["name"], "r": u["role"]}, "Logged in"); return pub(u)

@router.get("/api/me")
async def me(req: Request):
    u = auth(req); r = db("SELECT * FROM users WHERE name=?", (u["n"],), one=True)
    if not r: raise HTTPException(401, "Please log in")
    return pub(r)

@router.post("/api/password")
async def password(req: Request):
    u = auth(req); b = await req.json(); r = db("SELECT * FROM users WHERE name=?", (u["n"],), one=True)
    if not check(r["pw"], b.get("old", "")): raise HTTPException(400, "Current password is wrong")
    if not strong(b.get("new", "")): raise HTTPException(400, "Password needs 8+ characters with a letter and a number")
    db("UPDATE users SET pw=? WHERE name=?", (H(b["new"]), u["n"])); log(u, "Changed password"); return {"ok": 1}

@router.post("/api/check")
async def live(req: Request):
    auth(req); b = await req.json()
    F, _ = analyze(b.get("text", ""), b.get("meta", {"fg": "#000000", "bg": "#ffffff"}), b.get("channel", ""), use_ai=False); return F
