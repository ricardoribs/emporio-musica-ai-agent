from pathlib import Path
from typing import ClassVar

from httpx2 import TimeoutException

from emporio_agent.config import Settings
from emporio_agent.evaluation import (
    EvalTurn,
    evaluate_turn,
    load_cases,
    render_report,
    respond_with_retry,
    run_suite,
)


class FakeAgent:
    responses: ClassVar[list[str]] = []
    instances: ClassVar[list["FakeAgent"]] = []

    def __init__(self, _settings: Settings) -> None:
        self.response = self.responses.pop(0)
        self.closed = False
        self.instances.append(self)

    def respond(self, _message: str) -> str:
        return self.response

    def close(self) -> None:
        self.closed = True


def test_loads_five_documented_cases() -> None:
    cases = load_cases()

    assert len(cases) == 5
    assert {case.case_id for case in cases} == {
        "catalog_budget",
        "active_promotions",
        "online_return_policy",
        "order_identity",
        "out_of_scope",
    }


def test_evaluates_required_groups_without_accents_or_case() -> None:
    turn = EvalTurn(
        prompt="teste",
        required=(("e-mail", "email"), ("7 dias corridos",)),
        forbidden=("30 dias",),
    )

    result = evaluate_turn(turn, "O EMAIL confirma o prazo de 7 DIAS CORRIDOS.")

    assert result.passed is True
    assert result.missing_groups == ()
    assert result.forbidden_matches == ()


def test_reports_missing_and_forbidden_content() -> None:
    turn = EvalTurn(
        prompt="teste",
        required=(("embalagem original",),),
        forbidden=("30 dias",),
    )

    result = evaluate_turn(turn, "O prazo é de 30 dias.")

    assert result.passed is False
    assert result.missing_groups == (("embalagem original",),)
    assert result.forbidden_matches == ("30 dias",)


def test_retries_transient_timeout() -> None:
    class FlakyAgent:
        calls = 0

        def respond(self, _message: str) -> str:
            self.calls += 1
            if self.calls == 1:
                raise TimeoutException("timeout")
            return "resposta recuperada"

        def close(self) -> None:
            pass

    agent = FlakyAgent()

    response = respond_with_retry(agent, "teste", retry_delays=(0,))

    assert response == "resposta recuperada"
    assert agent.calls == 2


def test_runs_cases_in_isolated_agents_and_renders_report(tmp_path: Path) -> None:
    FakeAgent.responses = [
        "Shelby SN-100 custa R$ 549,00 e é uma boa opção para iniciante.",
        "Há ofertas Ohana CK-20, Crafter HT-100, Kalani KAL-700T e Taylor 110e.",
    ]
    FakeAgent.instances = []
    cases = load_cases()[:2]
    settings = Settings(gemini_api_key="test-key", gemini_model="test-model")

    results = run_suite(cases, settings, agent_factory=FakeAgent)
    report = render_report(results, settings.gemini_model)
    report_path = tmp_path / "report.md"
    report_path.write_text(report, encoding="utf-8")

    assert all(result.passed for result in results)
    assert all(agent.closed for agent in FakeAgent.instances)
    assert "2/2 cenários aprovados" in report_path.read_text(encoding="utf-8")
