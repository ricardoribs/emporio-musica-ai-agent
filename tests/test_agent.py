from types import SimpleNamespace

import pytest
from google.genai import types

from emporio_agent.agent import (
    SYSTEM_INSTRUCTION,
    EmporioAgent,
    EmptyModelResponseError,
)
from emporio_agent.config import Settings


class FakeChat:
    def __init__(self, responses: list[str | None]) -> None:
        self.responses = responses
        self.messages: list[str] = []

    def send_message(self, message: str) -> SimpleNamespace:
        self.messages.append(message)
        return SimpleNamespace(text=self.responses.pop(0))


class FakeChats:
    def __init__(self, chat: FakeChat) -> None:
        self.chat = chat
        self.model: str | None = None
        self.config: types.GenerateContentConfig | None = None

    def create(
        self,
        *,
        model: str,
        config: types.GenerateContentConfig,
    ) -> FakeChat:
        self.model = model
        self.config = config
        return self.chat


class FakeClient:
    def __init__(self, chat: FakeChat) -> None:
        self.chats = FakeChats(chat)


def build_agent(
    responses: list[str | None],
) -> tuple[EmporioAgent, FakeClient, FakeChat]:
    chat = FakeChat(responses)
    client = FakeClient(chat)
    settings = Settings(
        gemini_api_key="test-key",
        gemini_model="test-model",
    )
    agent = EmporioAgent(settings, client=client)
    return agent, client, chat


def test_configures_chat_with_model_and_tools() -> None:
    _, client, _ = build_agent(["Olá!"])

    assert client.chats.model == "test-model"

    config = client.chats.config
    assert config is not None
    assert config.system_instruction == SYSTEM_INSTRUCTION
    assert config.tools is not None
    assert len(config.tools) == 5
    assert config.automatic_function_calling is not None
    assert config.automatic_function_calling.maximum_remote_calls == 6
    assert config.thinking_config is not None
    assert config.thinking_config.thinking_level is types.ThinkingLevel.LOW


def test_uses_same_chat_for_conversation_history() -> None:
    agent, _, chat = build_agent(
        [
            "Temos algumas opções.",
            "A segunda é uma boa escolha.",
        ],
    )

    first_response = agent.respond("Quero um violão.")
    second_response = agent.respond("Fale mais sobre a segunda opção.")

    assert first_response == "Temos algumas opções."
    assert second_response == "A segunda é uma boa escolha."
    assert chat.messages == [
        "Quero um violão.",
        "Fale mais sobre a segunda opção.",
    ]


def test_rejects_empty_message() -> None:
    agent, _, chat = build_agent(["não utilizada"])

    with pytest.raises(ValueError, match="não pode estar vazia"):
        agent.respond("   ")

    assert chat.messages == []


def test_rejects_empty_model_response() -> None:
    agent, _, _ = build_agent([None])

    with pytest.raises(EmptyModelResponseError):
        agent.respond("Olá")
