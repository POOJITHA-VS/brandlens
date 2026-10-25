# BrandLens: pre-publication brand governance

Team CODEX · Inkloom AI · Problem: Intelligent Brand Governance · Participant: VS Poojitha (solo)

BrandLens reviews content against approved guidelines and facts **before** it is published. Every finding cites a guideline clause or approved fact (no citation, no finding), is explained in plain language with a confidence level, and ends in a human decision.

## Run it
```
pip install -r requirements.txt
cd backend
python main.py          # open http://localhost:8000
```
Open the site, choose **Create account**, pick a role (Creator, Manager, Reviewer or Admin) and set your own password. Passwords are stored salted and hashed (PBKDF2) in the SQLite database; sessions use signed tokens, and repeated failed logins are rate-limited. To follow the whole workflow, create one account per role (sign out in between). Set `BL_ADMIN_CODE` to require a code for Admin sign-ups. Tests: `python tests/test_flow.py`.
Optional: `export ANTHROPIC_API_KEY=...` turns on the Claude tone/messaging layer (off by default).

## Structure
```
backend/   config.py, database.py (SQLite), auth.py (tokens, roles, audit chain), engine.py (rules + claim checker),
           ai.py (redaction + Claude + validator), routes_*.py (REST API), main.py
frontend/  index.html, style.css, app.js (single-page app: auth, dashboard, review, insights)
tests/     test_flow.py (end-to-end)
```
Stack: FastAPI, SQLite, vanilla JS. Changes from the Round 1 plan: SQLite instead of PostgreSQL + pgvector, and a FastAPI-served frontend instead of Next.js.

## Feature status
Built: sign-up with chosen role and password, dashboard, roles and login · knowledge base (clauses, facts with owner/expiry, glossary, brand voice sample) · guideline import to clauses · submission with channel and purpose · rule checks (terminology, tone, readability, contrast, alt text) · claim checker (supported / contradicted / outdated / no evidence) · explained findings with citation and confidence · "needs human judgement" for low confidence · accept/dismiss with reason · versions with diff · comments · request changes / Reviewer-only approval (blocked while high-severity findings are open) · hash-chained audit log · Brand Health Score and risk meter · live check · fact-expiry alerts · what-if test · wrong-flag button and precision estimate · Guideline Clarity and rule-conflict finder (simple) · approved text export with stamp.

Partial: per-channel rules (exclamation limit only) · redaction (emails, phones, amounts; not names) · brand voice match (word overlap) · Claude layer (implemented, needs a key, not tested live).

Not built: image review beyond contrast/alt text (no OCR, logo or palette check) · Word/PDF export · confidential-mode toggle.

## AI and privacy disclosure
Rules run on the server. The Claude API is called only if `ANTHROPIC_API_KEY` is set, after redaction, and its findings are dropped unless the cited clause exists and the quoted text is really in the draft. AI only suggests; accept, dismiss, and approve are human actions.
