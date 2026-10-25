"""SQLite schema, seed data and query helper."""
import sqlite3, hashlib, hmac, secrets
from datetime import date, timedelta
from config import DB, SECRET

def db(sql, a=(), one=False):
    c = sqlite3.connect(DB); c.row_factory = sqlite3.Row
    try:
        cur = c.execute(sql, a)
        if sql.lstrip()[:6] == "INSERT": c.commit(); return cur.lastrowid
        r = cur.fetchone() if one else cur.fetchall(); c.commit()
        return (dict(r) if r else None) if one else [dict(x) for x in r]
    finally: c.close()

SCHEMA = """CREATE TABLE IF NOT EXISTS users(name TEXT PRIMARY KEY,full TEXT,role TEXT,team TEXT,pw TEXT,created REAL);
CREATE TABLE IF NOT EXISTS clauses(id TEXT PRIMARY KEY,sec TEXT,text TEXT);
CREATE TABLE IF NOT EXISTS facts(id TEXT PRIMARY KEY,key TEXT,text TEXT,value TEXT,owner TEXT,expiry TEXT);
CREATE TABLE IF NOT EXISTS gloss(bad TEXT PRIMARY KEY,good TEXT);
CREATE TABLE IF NOT EXISTS settings(k TEXT PRIMARY KEY,v TEXT);
CREATE TABLE IF NOT EXISTS subs(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,channel TEXT,purpose TEXT,team TEXT,author TEXT,status TEXT,draft TEXT,meta TEXT,appr TEXT,created REAL);
CREATE TABLE IF NOT EXISTS vers(id INTEGER PRIMARY KEY AUTOINCREMENT,sub INTEGER,n INTEGER,text TEXT,findings TEXT,voice REAL,ai TEXT,ts REAL);
CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY AUTOINCREMENT,sub INTEGER,n INTEGER,who TEXT,text TEXT,ts REAL);
CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,ts REAL,who TEXT,action TEXT,prev TEXT,hash TEXT);
CREATE TABLE IF NOT EXISTS fb(sub INTEGER,n INTEGER,fid TEXT,ref TEXT);"""
def H(p, salt=None):
    salt = salt or secrets.token_hex(8)
    return salt + "$" + hashlib.pbkdf2_hmac("sha256", p.encode(), salt.encode() + SECRET, 120000).hex()
def check(stored, p): return hmac.compare_digest(H(p, stored.split("$")[0]), stored)

def init():
    c = sqlite3.connect(DB); c.executescript(SCHEMA); c.commit()
    if not c.execute("SELECT 1 FROM users").fetchone():
        c.executemany("INSERT INTO users VALUES(?,?,?,?,?,?)", [(n, n.title(), r, t, H("demo123"), 0) for n, r, t in [("asha", "Creator", "Marketing"), ("rahul", "Creator", "Design"), ("meera", "Manager", "Marketing"), ("ravi", "Reviewer", "Legal"), ("admin", "Admin", "Brand")]])
        c.executemany("INSERT INTO clauses VALUES(?,?,?)", [
            ("T-1", "Tone", "Use a warm, professional tone. Avoid hype and slang. Keep exclamation marks to the channel limit."),
            ("T-2", "Tone", "Do not write words in ALL CAPS for emphasis."),
            ("M-1", "Messaging", "Never use unsupported superlatives (best, #1, leading, guaranteed) unless an approved fact backs them."),
            ("M-2", "Messaging", "Prices, statistics, ratings and dates must match approved facts. Unverifiable statistics need reviewer sign-off."),
            ("L-1", "Terminology", "Use preferred terms from the glossary; avoid the banned alternatives."),
            ("R-1", "Readability", "Keep sentences under 25 words where possible."),
            ("V-1", "Visual", "Text and background must meet WCAG AA contrast of at least 4.5:1."),
            ("A-1", "Accessibility", "Every image must have descriptive alt text.")])
        c.executemany("INSERT INTO facts VALUES(?,?,?,?,?,?)", [
            ("F-1", "price", "Starter plan costs ₹499 per month", "499", "Finance", "2027-03-31"),
            ("F-2", "founded", "Company founded in 2019", "2019", "Admin", "2099-01-01"),
            ("F-3", "customers", "Used by 2,000+ teams", "2,000", "Sales", "2026-06-30"),
            ("F-4", "rating", "Customer rating 4.6/5", "4.6", "Support", (date.today() + timedelta(days=20)).isoformat())])
        c.executemany("INSERT INTO gloss VALUES(?,?)", [("users", "members"), ("cheap", "affordable"), ("utilize", "use"), ("guys", "everyone")])
        c.execute("INSERT INTO settings VALUES('voice','We help teams publish with confidence. Our approach is clear, warm and professional. Members get practical guidance, honest results and helpful support.')")
        c.commit()
    c.close()

