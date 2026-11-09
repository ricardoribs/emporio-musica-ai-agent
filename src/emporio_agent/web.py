from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock
from typing import Any, Protocol
from uuid import UUID

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from google.genai import errors
from httpx2 import TimeoutException
from pydantic import BaseModel, Field

from emporio_agent.agent import EmporioAgent, EmptyModelResponseError
from emporio_agent.cli import api_error_message
from emporio_agent.config import Settings, get_settings

INDEX_PATH = Path(__file__).with_name("static") / "index.html"


class Agent(Protocol):
    def respond(self, message: str) -> str: ...

    def close(self) -> None: ...


@dataclass(slots=True)
class AgentSession:
    agent: Agent
    lock: Any = field(default_factory=Lock)


class SessionStore:
    def __init__(
        self,
        settings_factory: Callable[[], Settings] = get_settings,
        agent_factory: Callable[[Settings], Agent] = EmporioAgent,
    ) -> None:
        self._settings_factory = settings_factory
        self._agent_factory = agent_factory
        self._sessions: dict[UUID, AgentSession] = {}
        self._lock = Lock()

    def get_or_create(self, session_id: UUID) -> AgentSession:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = AgentSession(
                    agent=self._agent_factory(self._settings_factory()),
                )
                self._sessions[session_id] = session
            return session

    def respond(self, session_id: UUID, message: str) -> str:
        session = self.get_or_create(session_id)
        with session.lock:
            return session.agent.respond(message)

    def reset(self, session_id: UUID) -> None:
        with self._lock:
            session = self._sessions.pop(session_id, None)

        if session is not None:
            with session.lock:
                session.agent.close()

    def close_all(self) -> None:
        with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()

        for session in sessions:
            with session.lock:
                session.agent.close()


class ChatRequest(BaseModel):
    session_id: UUID
    message: str = Field(min_length=1, max_length=500)


class ChatResponse(BaseModel):
    answer: str


class ResetRequest(BaseModel):
    session_id: UUID


class ResetResponse(BaseModel):
    reset: bool


session_store = SessionStore()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    session_store.close_all()


app = FastAPI(
    title="Empório da Música",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/", response_class=FileResponse, include_in_schema=False)
def read_index() -> FileResponse:
    return FileResponse(
        path=INDEX_PATH,
        media_type="text/html",
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="A mensagem não pode estar vazia.")

    try:
        answer = session_store.respond(request.session_id, message)
    except TimeoutException as error:
        raise HTTPException(
            status_code=504,
            detail="A API demorou mais de 30 segundos para responder.",
        ) from error
    except errors.APIError as error:
        status_code = error.code if 400 <= error.code <= 599 else 502
        raise HTTPException(
            status_code=status_code,
            detail=api_error_message(error.code),
        ) from error
    except (EmptyModelResponseError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    return ChatResponse(answer=answer)


@app.post("/api/reset", response_model=ResetResponse)
def reset(request: ResetRequest) -> ResetResponse:
    session_store.reset(request.session_id)
    return ResetResponse(reset=True)


def main() -> None:
    uvicorn.run(
        "emporio_agent.web:app",
        host="127.0.0.1",
        port=8000,
        reload=False,
    )
