from google.genai import errors
from httpx2 import TimeoutException
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from emporio_agent.agent import EmporioAgent, EmptyModelResponseError
from emporio_agent.config import get_settings

console = Console()

EXIT_COMMANDS = {
    "/sair",
    "sair",
    "exit",
    "quit",
}


def is_exit_command(message: str) -> bool:
    return message.strip().casefold() in EXIT_COMMANDS


def api_error_message(status_code: int) -> str:
    if status_code in {401, 403}:
        return "A chave da API foi recusada. Verifique GEMINI_API_KEY no arquivo .env."

    if status_code == 404:
        return "O modelo configurado não foi encontrado ou não está disponível para esta chave."

    if status_code == 429:
        return "O limite gratuito da API foi atingido. Aguarde e tente novamente mais tarde."

    if status_code >= 500:
        return "O serviço do Gemini está temporariamente indisponível."

    return "Não foi possível concluir a solicitação com o Gemini."


def run_chat(agent: EmporioAgent) -> None:
    while True:
        try:
            message = Prompt.ask("\n[bold cyan]Você[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Atendimento encerrado.[/dim]")
            return

        if is_exit_command(message):
            console.print("[dim]Atendimento encerrado. Até a próxima![/dim]")
            return

        if not message.strip():
            continue

        try:
            with console.status(
                "[bold yellow]Bia está consultando as informações...[/bold yellow]",
            ):
                response = agent.respond(message)
        except TimeoutException:
            console.print(
                "[bold red]Tempo limite:[/bold red] "
                "A API demorou mais de 30 segundos para responder.",
            )
            return
        except errors.APIError as error:
            console.print(
                f"[bold red]Erro na API:[/bold red] {api_error_message(error.code)}",
            )
            return
        except (EmptyModelResponseError, ValueError) as error:
            console.print(f"[bold red]Não foi possível responder:[/bold red] {error}")
            continue

        console.print(
            Panel(
                Markdown(response),
                title="[bold magenta]Bia[/bold magenta]",
                border_style="magenta",
                padding=(1, 2),
            ),
        )


def main() -> None:
    try:
        settings = get_settings()
    except RuntimeError as error:
        console.print(f"[bold red]Erro de configuração:[/bold red] {error}")
        raise SystemExit(1) from error

    console.print(
        Panel.fit(
            "[bold]Empório da Música[/bold]\n"
            "Atendimento virtual para produtos, pedidos e políticas da loja.",
            border_style="cyan",
        ),
    )
    console.print(
        f"[dim]Modelo: {settings.gemini_model} | Digite /sair para encerrar.[/dim]",
    )

    with EmporioAgent(settings) as agent:
        run_chat(agent)


if __name__ == "__main__":
    main()
