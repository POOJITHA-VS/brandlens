"""Claude layer: redaction before the call, and a validator that rejects unverifiable findings."""
import re, json, urllib.request
from database import db
from config import KEY, MODEL

def redact(t):
    t = re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[EMAIL]", t)
    t = re.sub(r"(₹|\$|Rs\.?)\s?[\d,]+", "[AMOUNT]", t)
    return re.sub(r"\+?\d[\d\s-]{8,}\d", "[PHONE]", t)

def ai_check(text, purpose):
    if not KEY: return [], "off (no ANTHROPIC_API_KEY set)"
    cl = db("SELECT * FROM clauses WHERE sec IN ('Tone','Messaging')"); red = redact(text)
    prompt = ("You are a brand reviewer. Use ONLY these guideline clauses:\n" + "\n".join(f'{c["id"]}: {c["text"]}' for c in cl) +
              f"\n\nCreator purpose (must be preserved): {purpose}\n\nText:\n{red}\n\nReturn ONLY a JSON array of tone or messaging problems: "
              '[{"ref":"<clause id>","quote":"<exact text copied from the text>","reason":"...","confidence":0-1,"fix":"<rewrite of the quote that keeps the purpose>"}]. Return [] if none.')
    try:
        r = urllib.request.Request("https://api.anthropic.com/v1/messages", json.dumps({"model": MODEL, "max_tokens": 1200, "messages": [{"role": "user", "content": prompt}]}).encode(),
                                   {"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        out = json.load(urllib.request.urlopen(r, timeout=30))["content"][0]["text"]
        arr = json.loads(re.search(r"\[.*\]", out, re.S).group(0))
    except Exception as e: return [], "error: " + str(e)[:80]
    ids = {c["id"] for c in cl}; res = []; rej = 0
    for a in arr:  # validator: cited clause must exist and quote must really be in the text
        r_, q = a.get("ref"), str(a.get("quote", ""))
        if r_ in ids and q and q in text and q in red:
            res.append({"cat": "Tone", "sev": "medium", "ref": r_, "q": q, "i": text.find(q), "reason": "AI: " + str(a.get("reason", ""))[:200],
                        "conf": max(0, min(1, float(a.get("confidence", .6)))), "fix": a.get("fix") or None, "src": "ai", "claim": None})
        else: rej += 1
    return res, f"on ({MODEL}); text redacted before sending; {rej} unverifiable finding(s) rejected"

