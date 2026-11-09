from emporio_agent.config import Settings


def test_default_model() -> None:
    settings = Settings(gemini_api_key="test-key")

    assert settings.gemini_model == "gemini-2.5-flash"
