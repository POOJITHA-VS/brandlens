"""End-to-end API test: submit -> check -> fix -> version -> review -> approve -> export -> audit."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ["BL_DB"] = os.path.join(tempfile.mkdtemp(), "t.db")
from fastapi.testclient import TestClient
from main import app
c = TestClient(app)
TEXT = ("Meet BrandLens, the BEST platform for teams! We are the #1 choice in India and our users love us!! Over 5,000 teams rely on us, "
        "and our Starter plan is just \u20b9399 per month. Since 2018 we have been helping guys publish faster, with 98% accuracy. It is gonna be awesome.")

def login(n):
    return {"authorization": "Bearer " + c.post("/api/login", json={"name": n, "pw": "demo123"}).json()["token"]}

def test_full_flow():
    a, m, r, ad = map(login, ("asha", "meera", "ravi", "admin"))
    assert c.get("/api/subs").status_code == 401
    assert c.post("/api/login", json={"name": "asha", "pw": "bad"}).status_code == 401
    s = c.post("/api/subs", headers=a, json={"title": "T", "channel": "LinkedIn post", "purpose": "p", "text": TEXT,
               "meta": {"fg": "#9a9a9a", "bg": "#ffffff", "img": True, "alt": ""}}).json()["id"]
    get = lambda: c.get(f"/api/subs/{s}", headers=a).json()
    F = get()["vers"][0]["findings"]
    assert len(F) >= 10 and all(f["ref"] for f in F)
    assert {f["claim"] for f in F} >= {"contradicted", "no_evidence"}
    for f in F:
        cur = next(x for x in get()["vers"][0]["findings"] if x["id"] == f["id"])
        if cur["status"] == "open" and cur["fix"]:
            x = c.post(f"/api/subs/{s}/finding", headers=a, json={"fid": f["id"], "action": "accept"}); assert x.status_code == 200, (f["ref"], f["q"], x.text)
    draft = get()["sub"]["draft"]
    assert "!!" not in draft and "\u20b9499" in draft and "members" in draft and "BEST" not in draft
    assert c.post(f"/api/subs/{s}/version", headers=a).json()["n"] == 2
    for f in get()["vers"][-1]["findings"]:
        if f["status"] == "open":
            assert c.post(f"/api/subs/{s}/finding", headers=a, json={"fid": f["id"], "action": "dismiss", "reason": "ok"}).status_code == 200
    assert c.post(f"/api/subs/{s}/send", headers=a).status_code == 200
    assert c.post(f"/api/subs/{s}/decision", headers=m, json={"d": "approve"}).status_code == 403
    assert c.post(f"/api/subs/{s}/decision", headers=r, json={"d": "approve"}).status_code == 200
    assert "approval stamp" in c.get(f"/api/subs/{s}/export", headers=r).text
    assert c.post("/api/kb/gloss", headers=a, json={"bad": "x", "good": "y"}).status_code == 403
    assert c.get("/api/audit", headers=ad).json()["ok"]
    assert c.get("/api/insights", headers=ad).json()["cat"]
    assert c.get("/").status_code == 200 and c.get("/static/app.js").status_code == 200

def test_accounts():
    r = lambda **k: c.post("/api/register", json=k)
    ok = dict(name="priya_k", full="Priya K", pw="Strong123", role="Reviewer", team="Legal")
    assert r(**ok).status_code == 200 and r(**ok).status_code == 409
    assert r(**{**ok, "name": "x1", "pw": "short"}).status_code == 400 and r(**{**ok, "name": "x2", "role": "Boss"}).status_code == 400
    assert c.post("/api/login", json={"name": "priya_k", "pw": "Strong123"}).json()["role"] == "Reviewer"
    assert c.post("/api/login", json={"name": "priya_k", "pw": "nope"}).status_code == 401
    h = {"authorization": "Bearer " + c.post("/api/login", json={"name": "priya_k", "pw": "Strong123"}).json()["token"]}
    assert c.get("/api/me", headers=h).json()["full"] == "Priya K" and c.get("/api/stats", headers=h).status_code == 200
    assert c.post("/api/password", headers=h, json={"old": "Strong123", "new": "Better4567"}).status_code == 200
    assert c.post("/api/login", json={"name": "priya_k", "pw": "Better4567"}).status_code == 200

if __name__ == "__main__":
    test_accounts(); test_full_flow(); print("all checks passed")
