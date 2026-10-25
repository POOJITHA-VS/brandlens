"""BrandLens entry point. Run:  python main.py  ->  http://localhost:8000"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from database import init
from routes_auth import router as auth_r
from routes_kb import router as kb_r
from routes_subs import router as subs_r
from routes_insights import router as ins_r

init()
app = FastAPI(title="BrandLens")
for r in (auth_r, kb_r, subs_r, ins_r): app.include_router(r)
FRONT = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONT), name="static")

@app.get("/")
async def home(): return FileResponse(FRONT / "index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
