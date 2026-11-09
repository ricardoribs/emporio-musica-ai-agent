from uuid import uuid4

from fastapi.testclient import TestClient

import emporio_agent.web as web_module
from emporio_agent.config import Settings
from emporio_agent.web import SessionStore, app


class FakeAgent:
    def __init__(self, _: Settings) -> None:
        self.received_messages: list[str] = []
        self.closed = False

    def respond(self, message: str) -> str:
        self.received_messages.append(message)
        return "Resposta fundamentada de teste."

    def close(self) -> None:
        self.closed = True


def build_store() -> tuple[SessionStore, list[FakeAgent]]:
    agents: list[FakeAgent] = []

    def create_agent(settings: Settings) -> FakeAgent:
        agent = FakeAgent(settings)
        agents.append(agent)
        return agent

    store = SessionStore(
        settings_factory=lambda: Settings(
            gemini_api_key="test-key",
            gemini_model="test-model",
        ),
        agent_factory=create_agent,
    )
    return store, agents


def test_serves_reference_interface(monkeypatch) -> None:
    store, _ = build_store()
    monkeypatch.setattr(web_module, "session_store", store)

    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "Empório da Música" in response.text
    assert "Perguntas frequentes" in response.text
    assert "api/chat" in response.text


def test_chat_preserves_session_and_reset_closes_agent(monkeypatch) -> None:
    store, agents = build_store()
    monkeypatch.setattr(web_module, "session_store", store)
    session_id = str(uuid4())

    with TestClient(app) as client:
        first_response = client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "Vocês têm violões?",
            },
        )
        second_response = client.post(
            "/api/chat",
            json={
                "session_id": session_id,
                "message": "Qual é o mais barato?",
            },
        )
        reset_response = client.post(
            "/api/reset",
            json={"session_id": session_id},
        )

    assert first_response.json() == {"answer": "Resposta fundamentada de teste."}
    assert second_response.status_code == 200
    assert len(agents) == 1
    assert agents[0].received_messages == [
        "Vocês têm violões?",
        "Qual é o mais barato?",
    ]
    assert reset_response.json() == {"reset": True}
    assert agents[0].closed is True
