from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import List
import io
import csv
import zipfile

import orjson
from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select

from .database import init_db, get_session, DATA_DIR, BASE_DIR
from .models import UploadRecord
from .schemas import UploadResponse, HistoryItem, ResultResponse
from .services.pdf_tables import extract_tables
from .services.ollama_clean import clean_tables_with_ollama
from sqlmodel import Session

app = FastAPI(title="GenAI PDF Table Extractor", version="0.1.0")

# CORS for local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure data/upload dirs
UPLOADS_DIR = BASE_DIR / "backend" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# Static front-end
FRONTEND_DIR = BASE_DIR / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
async def root_index():
    index_path = FRONTEND_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.post("/api/upload", response_model=UploadResponse)
async def upload_pdf(
    file: UploadFile = File(...),
    use_llm: bool = Query(False, description="Whether to use Llama3 via Ollama for cleanup"),
    session: Session = Depends(get_session),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")

    # Save file
    uid = str(uuid.uuid4())
    save_path = UPLOADS_DIR / f"{uid}_{file.filename}"
    content = await file.read()
    save_path.write_bytes(content)

    # Extract tables
    tables = extract_tables(save_path)

    # Optional LLM cleanup
    if use_llm and tables:
        tables = await clean_tables_with_ollama(tables)

    # Persist record
    result_json = json.dumps(tables, ensure_ascii=False)
    rec = UploadRecord(
        id=uid,
        filename=file.filename,
        created_at=datetime.utcnow(),
        use_llm=use_llm,
        table_count=len(tables),
        result_json=result_json,
    )
    session.add(rec)
    session.commit()

    return UploadResponse(
        id=rec.id,
        filename=rec.filename,
        created_at=rec.created_at,
        table_count=rec.table_count,
    )


@app.get("/api/history", response_model=List[HistoryItem])
async def get_history(session: Session = Depends(get_session)):
    rows = session.exec(select(UploadRecord).order_by(UploadRecord.created_at.desc())).all()
    return [
        HistoryItem(
            id=r.id,
            filename=r.filename,
            created_at=r.created_at,
            table_count=r.table_count,
            use_llm=r.use_llm,
        )
        for r in rows
    ]


@app.get("/api/result/{uid}", response_model=ResultResponse)
async def get_result(uid: str, session: Session = Depends(get_session)):
    rec = session.get(UploadRecord, uid)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    tables = json.loads(rec.result_json) if rec.result_json else []
    return ResultResponse(
        id=rec.id,
        filename=rec.filename,
        created_at=rec.created_at,
        use_llm=rec.use_llm,
        tables=tables,
    )


@app.get("/api/download/{uid}.json")
async def download_json(uid: str, session: Session = Depends(get_session)):
    rec = session.get(UploadRecord, uid)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")

    def iter_json_bytes():
        yield rec.result_json.encode("utf-8")

    headers = {
        "Content-Disposition": f"attachment; filename=tables_{uid}.json",
        "Content-Type": "application/json",
    }
    return StreamingResponse(iter_json_bytes(), media_type="application/json", headers=headers)


@app.get("/api/export/{uid}/table.csv")
async def export_single_csv(
    uid: str,
    page: int = Query(..., ge=1, description="Page number (1-based)"),
    table_index: int = Query(..., ge=0, description="Table index on the page (0-based)"),
    session: Session = Depends(get_session),
):
    rec = session.get(UploadRecord, uid)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    tables = json.loads(rec.result_json) if rec.result_json else []
    target = next((t for t in tables if t.get("page") == page and t.get("table_index") == table_index), None)
    if not target:
        raise HTTPException(status_code=404, detail="Table not found for given page and table_index")

    output = io.StringIO()
    writer = csv.writer(output)
    headers = target.get("headers") or []
    rows = target.get("rows") or []
    if headers:
        writer.writerow(headers)
    for r in rows:
        writer.writerow(["" if (c is None) else c for c in r])

    filename = f"tables_{uid}_p{page}_t{table_index}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.get("/api/export/{uid}/all.zip")
async def export_all_zip(uid: str, session: Session = Depends(get_session)):
    rec = session.get(UploadRecord, uid)
    if not rec:
        raise HTTPException(status_code=404, detail="Not found")
    tables = json.loads(rec.result_json) if rec.result_json else []
    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for t in tables:
            page = t.get("page")
            ti = t.get("table_index")
            headers = t.get("headers") or []
            rows = t.get("rows") or []
            sio = io.StringIO()
            writer = csv.writer(sio)
            if headers:
                writer.writerow(headers)
            for r in rows:
                writer.writerow(["" if (c is None) else c for c in r])
            zf.writestr(f"page_{page}_table_{ti}.csv", sio.getvalue())
    mem.seek(0)
    return StreamingResponse(
        mem,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=tables_{uid}.zip"},
    )
