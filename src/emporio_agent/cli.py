from rich.console import Console

from emporio_agent.config import get_settings

console = Console()


def main() -> None:
    try:
        settings = get_settings()
    except RuntimeError as error:
        console.print(f"[bold red]Erro de configuração:[/bold red] {error}")
        raise SystemExit(1) from error

    console.print("[bold green]Configuração carregada com sucesso.[/bold green]")
    console.print(f"Modelo configurado: {settings.gemini_model}")


if __name__ == "__main__":
    main()
