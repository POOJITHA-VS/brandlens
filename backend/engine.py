"""Deterministic review engine: terms, claims vs approved facts, tone, readability, contrast, alt text."""
import re
from datetime import date
from database import db
from ai import ai_check

SUP = {"best": "trusted", "#1": "trusted", "number one": "trusted", "world-class": "high-quality", "unbeatable": "competitive", "guaranteed": "designed to deliver", "market leader": "growing provider", "industry-leading": "well-regarded", "leading": "well-regarded"}
MAXEX = {"Press release": 0, "Ad": 2, "Blog": 1, "LinkedIn post": 1, "Deck": 1}
def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    c = [v / 12.92 if v <= .03928 else ((v + .055) / 1.055) ** 2.4 for v in c]
    return .2126 * c[0] + .7152 * c[1] + .0722 * c[2]
def ratio(a, b):
    x, y = lum(a), lum(b); return (max(x, y) + .05) / (min(x, y) + .05)
def analyze(t, meta, channel, purpose="", use_ai=True):
    F = []; today = date.today().isoformat()
    kb = {k: db(f"SELECT * FROM {k}") for k in ("clauses", "facts", "gloss")}
    def add(**o): F.append({"status": "open", "src": "rule", "claim": None, "fix": None, **o})
    for g in kb["gloss"]:
        for x in re.finditer(r"\b" + re.escape(g["bad"]) + r"\b", t, re.I):
            add(cat="Terminology", sev="medium", ref="L-1", q=x.group(0), i=x.start(), conf=.95, fix=g["good"], reason=f"“{x.group(0)}” is not a preferred term; the glossary prefers “{g['good']}”.")
    for x in re.finditer(r"(#1|\b(best|number one|world-class|unbeatable|guaranteed|market leader|industry-leading|leading)\b)", t, re.I):
        k = x.group(0).lower()
        if any(k in f["text"].lower() for f in kb["facts"]): continue
        add(cat="Claims", sev="high", ref="M-1", q=x.group(0), i=x.start(), conf=.9, fix=SUP[k], claim="no_evidence", reason=f"Superlative “{x.group(0)}” has no approved fact behind it.")
    def num(key, pat, fix):
        f = next((f for f in kb["facts"] if f["key"] == key), None)
        if not f: return
        for x in re.finditer(pat, t, re.I):
            if x.group(1).replace(",", "") != f["value"].replace(",", ""):
                add(cat="Claims", sev="high", ref=f["id"], q=x.group(0), i=x.start(), conf=.9, claim="contradicted", fix=fix(x.group(0), f["value"]), reason=f"Contradicted: approved fact says “{f['text']}” (owner {f['owner']}).")
            elif f["expiry"] < today:
                add(cat="Claims", sev="medium", ref=f["id"], q=x.group(0), i=x.start(), conf=.6, claim="outdated", reason=f"Matches the fact, but it expired on {f['expiry']} (owner {f['owner']}). Confirm it is still true.")
            else:
                add(cat="Claims", sev="info", ref=f["id"], q=x.group(0), i=x.start(), conf=.95, claim="supported", status="info", reason=f"Supported by approved fact {f['id']}.")
    num("price", r"(?:₹|rs\.?\s?|inr\s?)\s?([\d,]+)", lambda q, v: re.sub(r"[\d,]+", v, q, 1))
    num("customers", r"([\d,]+)\+?\s*(?:teams|customers|clients)", lambda q, v: re.sub(r"[\d,]+", v, q, 1))
    num("founded", r"(?:since|founded in|established in)\s*(\d{4})", lambda q, v: re.sub(r"\d{4}", v, q))
    num("rating", r"(\d(?:\.\d)?)\s*/\s*5", lambda q, v: re.sub(r"^[\d.]+", v, q))
    for x in re.finditer(r"\b\d{1,3}(?:\.\d+)?\s?%", t):
        add(cat="Claims", sev="medium", ref="M-2", q=x.group(0), i=x.start(), conf=.5, claim="no_evidence", reason="Statistic with no approved fact. Cannot be verified; a human must decide.")
    n = 0
    for x in re.finditer(r"!", t):
        n += 1
        if n > MAXEX.get(channel, 1): add(cat="Tone", sev="low", ref="T-1", q="!", i=x.start(), conf=.85, fix=".", reason=f"More exclamation marks than the {channel} limit ({MAXEX.get(channel, 1)}).")
    for x in re.finditer(r"\b[A-Z]{4,}\b", t):
        add(cat="Tone", sev="low", ref="T-2", q=x.group(0), i=x.start(), conf=.8, fix=x.group(0).capitalize(), reason="ALL CAPS emphasis.")
    for x in re.finditer(r"\b(gonna|wanna|super|crazy|awesome|epic)\b", t, re.I):
        add(cat="Tone", sev="low", ref="T-1", q=x.group(0), i=x.start(), conf=.55, reason="Informal or hype wording; fit depends on the channel.")
    for x in re.finditer(r"[^.!?\n]+[.!?]*", t):
        s = x.group(0).strip()
        if len(s.split()) > 25: add(cat="Readability", sev="low", ref="R-1", q=s, i=x.start() + x.group(0).index(s), conf=.5, reason=f"Sentence has {len(s.split())} words (guideline: under 25).")
    r = ratio(meta.get("fg", "#000000"), meta.get("bg", "#ffffff"))
    if r < 4.5: add(cat="Accessibility", sev="high", ref="V-1", q=f'{meta["fg"]} on {meta["bg"]}', i=-1, conf=1, reason=f"Contrast ratio {r:.2f}:1; WCAG AA needs 4.5:1.")
    if meta.get("img") and not meta.get("alt", "").strip(): add(cat="Accessibility", sev="high", ref="A-1", q="(image)", i=-1, conf=1, reason="Image has no alt text.")
    ai = "off (live check)"
    if use_ai:
        res, ai = ai_check(t, purpose)
        for a in res: add(**a)
    ids = {c["id"] for c in kb["clauses"]} | {f["id"] for f in kb["facts"]}
    F = [f for f in F if f["ref"] in ids and (f["i"] < 0 or t[f["i"]:f["i"] + len(f["q"])] == f["q"])]  # no citation, no finding
    for j, f in enumerate(F): f["id"] = f"f{j}"
    return F, ai

W = lambda t: set(re.findall(r"[a-z]{4,}", t.lower()))
def voice(t):
    v = db("SELECT v FROM settings WHERE k='voice'", one=True); a, b = W(t), W(v["v"] if v else "")
    return round(min(100, 100 * len(a & b) / max(1, min(len(a), len(b)) * .5)), 1) if a and b else 0

def conflicts():
    pos, neg = [], []
    for c in db("SELECT * FROM clauses"):
        for m in re.finditer(r"\b(always|never|must not|do not|avoid|must|use)\s+(?:the\s+|a\s+)?([a-z]{4,})", c["text"].lower()):
            (neg if m.group(1) in ("never", "must not", "do not", "avoid") else pos).append((c["id"], m.group(2)))
    return [{"a": a, "b": b, "word": w} for a, w in pos for b, x in neg if w == x and a != b]

