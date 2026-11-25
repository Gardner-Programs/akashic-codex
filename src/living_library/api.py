from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .db import (
    connect,
    get_conversation,
    get_default_db_path,
    init_db,
    list_conversations,
)
from .ingest import save_conversation
from .search import search

DB_PATH = get_default_db_path()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db(str(DB_PATH))
    yield


app = FastAPI(
    title='Living Library',
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

STORE_HTML = Path(__file__).with_name('store.html')


def get_conn():
    conn = connect(str(DB_PATH))
    try:
        yield conn
    finally:
        conn.close()


class ConversationIn(BaseModel):
    full_log: str
    title: str | None = None
    source: str | None = None


class SavedConversation(BaseModel):
    id: int
    title: str
    summary: str
    source: str | None
    created_at: str


class SearchResult(BaseModel):
    id: int
    title: str
    summary: str
    source: str | None
    created_at: str


class ConversationPreview(BaseModel):
    id: int
    title: str
    summary: str
    source: str | None
    created_at: str


class Conversation(BaseModel):
    id: int
    title: str
    summary: str
    full_log: str
    source: str | None
    created_at: str


@app.post('/conversations', response_model=SavedConversation, status_code=201)
def save_conversation_endpoint(payload: ConversationIn, conn=Depends(get_conn)):
    conv_id = save_conversation(conn, payload.full_log, title=payload.title, source=payload.source)
    row = get_conversation(conn, conv_id)
    return SavedConversation(
        id=row['id'],
        title=row['title'],
        summary=row['summary'],
        source=row['source'],
        created_at=row['created_at'],
    )


@app.get('/search', response_model=list[SearchResult])
def search_conversation_endpoint(
    query: str = Query(min_length=1, description='search text'),
    limit: int = 5,
    conn=Depends(get_conn),
):
    results = search(conn, query, limit)
    return [
        SearchResult(
            id=r['id'],
            title=r['title'],
            summary=r['summary'],
            source=r['source'],
            created_at=r['created_at'],
        )
        for r in results
    ]


@app.get('/conversations', response_model=list[ConversationPreview])
def list_conversations_endpoint(
    limit: int = Query(default=20, ge=1, le=100), conn=Depends(get_conn)
):
    rows = list_conversations(conn, limit)
    return [
        ConversationPreview(
            id=row['id'],
            title=row['title'],
            summary=row['summary'],
            source=row['source'],
            created_at=row['created_at'],
        )
        for row in rows
    ]


@app.get('/conversations/{conv_id}', response_model=Conversation)
def get_conversation_endpoint(conv_id: int, conn=Depends(get_conn)):
    row = get_conversation(conn, conv_id)
    if not row:
        raise HTTPException(status_code=404, detail='Conversation not found')
    return Conversation(
        id=row['id'],
        title=row['title'],
        summary=row['summary'],
        full_log=row['full_log'],
        source=row['source'],
        created_at=row['created_at'],
    )


@app.get('/ui', response_class=HTMLResponse)
def store_ui():
    return HTMLResponse(STORE_HTML.read_text(encoding='utf-8'))


def run_api(host: str = '127.0.0.1', port: int = 8000, reload: bool = False):
    uvicorn.run('living_library.api:app', host=host, port=port, reload=reload)


if __name__ == '__main__':
    run_api()
