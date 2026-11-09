from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import sleep
from typing import Protocol
from unicodedata import normalize as unicode_normalize

from google.genai import errors
from httpx2 import TimeoutException
from rich.console import Console

from emporio_agent.agent import EmporioAgent
from emporio_agent.config import PROJECT_ROOT, Settings, get_settings

DEFAULT_CASES_PATH = PROJECT_ROOT / "evals" / "cases.json"
DEFAULT_REPORT_PATH = PROJECT_ROOT / "evals" / "latest_report.md"
RATE_LIMIT_RETRY_DELAYS = (5, 10, 20)


class AgentProtocol(Protocol):
    def respond(self, message: str) -> str: ...

    def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EvalTurn:
    prompt: str
    required: tuple[tuple[str, ...], ...]
    forbidden: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EvalCase:
    case_id: str
    title: str
    goal: str
    turns: tuple[EvalTurn, ...]


@dataclass(frozen=True, slots=True)
class TurnResult:
    prompt: str
    response: str
    matched_groups: tuple[str, ...]
    missing_groups: tuple[tuple[str, ...], ...]
    forbidden_matches: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.missing_groups and not self.forbidden_matches


@dataclass(frozen=True, slots=True)
class CaseResult:
    case: EvalCase
    turns: tuple[TurnResult, ...]
    error: str | None = None

    @property
    def passed(self) -> bool:
        return self.error is None and all(turn.passed for turn in self.turns)


def normalize_text(value: str) -> str:
    normalized = unicode_normalize("NFKD", value)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(ascii_text.casefold().split())


def load_cases(path: Path = DEFAULT_CASES_PATH) -> list[EvalCase]:
    raw_cases = json.loads(path.read_text(encoding="utf-8"))
    cases: list[EvalCase] = []

    for raw_case in raw_cases:
        turns = tuple(
            EvalTurn(
                prompt=turn["prompt"],
                required=tuple(tuple(group) for group in turn.get("required", [])),
                forbidden=tuple(turn.get("forbidden", [])),
            )
            for turn in raw_case["turns"]
        )
        cases.append(
            EvalCase(
                case_id=raw_case["id"],
                title=raw_case["title"],
                goal=raw_case["goal"],
                turns=turns,
            )
        )

    return cases


def evaluate_turn(turn: EvalTurn, response: str) -> TurnResult:
    normalized_response = normalize_text(response)
    matched_groups: list[str] = []
    missing_groups: list[tuple[str, ...]] = []

    for group in turn.required:
        match = next(
            (term for term in group if normalize_text(term) in normalized_response),
            None,
        )
        if match is None:
            missing_groups.append(group)
        else:
            matched_groups.append(match)

    forbidden_matches = tuple(
        term for term in turn.forbidden if normalize_text(term) in normalized_response
    )

    return TurnResult(
        prompt=turn.prompt,
        response=response,
        matched_groups=tuple(matched_groups),
        missing_groups=tuple(missing_groups),
        forbidden_matches=forbidden_matches,
    )


def respond_with_retry(
    agent: AgentProtocol,
    prompt: str,
    retry_delays: Sequence[int] = RATE_LIMIT_RETRY_DELAYS,
) -> str:
    for attempt in range(len(retry_delays) + 1):
        try:
            return agent.respond(prompt)
        except TimeoutException:
            if attempt == len(retry_delays):
                raise
            sleep(retry_delays[attempt])
        except errors.APIError as error:
            if error.code != 429 or attempt == len(retry_delays):
                raise
            sleep(retry_delays[attempt])

    raise RuntimeError("Número de tentativas excedido.")


def run_case(
    case: EvalCase,
    settings: Settings,
    agent_factory: Callable[[Settings], AgentProtocol] = EmporioAgent,
) -> CaseResult:
    agent = agent_factory(settings)
    results: list[TurnResult] = []

    try:
        for turn in case.turns:
            response = respond_with_retry(agent, turn.prompt)
            results.append(evaluate_turn(turn, response))
    except Exception as error:  # noqa: BLE001 - o relatório deve registrar falhas externas
        return CaseResult(case=case, turns=tuple(results), error=str(error))
    finally:
        agent.close()

    return CaseResult(case=case, turns=tuple(results))


def run_suite(
    cases: Sequence[EvalCase],
    settings: Settings,
    agent_factory: Callable[[Settings], AgentProtocol] = EmporioAgent,
) -> list[CaseResult]:
    return [run_case(case, settings, agent_factory) for case in cases]


def render_report(results: Sequence[CaseResult], model: str) -> str:
    passed = sum(result.passed for result in results)
    lines = [
        "# Relatório de avaliação",
        "",
        f"- Gerado em: {datetime.now(UTC).isoformat(timespec='seconds')}",
        f"- Modelo: `{model}`",
        f"- Resultado: **{passed}/{len(results)} cenários aprovados**",
        "- Método: verificações lexicais determinísticas sobre respostas do agente.",
        "",
    ]

    for result in results:
        status = "APROVADO" if result.passed else "REPROVADO"
        lines.extend(
            (
                f"## {result.case.title} — {status}",
                "",
                result.case.goal,
                "",
            )
        )

        if result.error:
            lines.extend((f"**Erro:** {result.error}", ""))

        for index, turn in enumerate(result.turns, start=1):
            lines.extend(
                (
                    f"### Turno {index}",
                    "",
                    f"**Usuário:** {turn.prompt}",
                    "",
                    f"**Bia:** {turn.response}",
                    "",
                    f"**Resultado:** {'aprovado' if turn.passed else 'reprovado'}",
                    "",
                )
            )
            if turn.missing_groups:
                missing = "; ".join(" / ".join(group) for group in turn.missing_groups)
                lines.extend((f"- Critérios ausentes: {missing}", ""))
            if turn.forbidden_matches:
                lines.extend(
                    (
                        f"- Conteúdo proibido encontrado: {', '.join(turn.forbidden_matches)}",
                        "",
                    )
                )

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Executa avaliações de ponta a ponta da Bia.")
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Executa somente o ID informado. Pode ser repetido.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    settings = get_settings()
    cases = load_cases(args.cases)

    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.case_id in selected]
        unknown = selected.difference(case.case_id for case in cases)
        if unknown:
            raise SystemExit(f"Cenário(s) desconhecido(s): {', '.join(sorted(unknown))}")

    if not cases:
        raise SystemExit("Nenhum cenário selecionado.")

    console = Console()
    console.print(f"Executando {len(cases)} cenário(s) com {settings.gemini_model}...")
    results = run_suite(cases, settings)
    report = render_report(results, settings.gemini_model)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")

    passed = sum(result.passed for result in results)
    for result in results:
        marker = "[green]APROVADO[/green]" if result.passed else "[red]REPROVADO[/red]"
        console.print(f"{marker}  {result.case.case_id} — {result.case.title}")

    console.print(f"Relatório: {args.output}")
    console.print(f"Resultado final: {passed}/{len(results)}")

    if passed != len(results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
