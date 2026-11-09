from emporio_agent.cli import api_error_message, is_exit_command


def test_recognizes_exit_commands() -> None:
    for command in ("/sair", "SAIR", " exit ", "Quit"):
        assert is_exit_command(command)

    assert not is_exit_command("Quero sair com um violão")


def test_translates_api_errors() -> None:
    assert "chave" in api_error_message(403)
    assert "modelo" in api_error_message(404)
    assert "limite gratuito" in api_error_message(429)
    assert "temporariamente indisponível" in api_error_message(500)
    assert "não foi possível" in api_error_message(400).casefold()
