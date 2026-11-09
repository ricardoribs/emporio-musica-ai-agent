import pytest

from emporio_agent.config import POLICIES_PATH
from emporio_agent.policy_retriever import PolicyRetriever


@pytest.fixture(scope="module")
def retriever() -> PolicyRetriever:
    return PolicyRetriever.from_pdf(POLICIES_PATH)


def test_extracts_all_policy_pages(retriever: PolicyRetriever) -> None:
    assert len(retriever.pages) == 8


def test_retrieves_return_policy(retriever: PolicyRetriever) -> None:
    results = retriever.search("Posso devolver uma compra online porque me arrependi?")

    assert results[0].page_number == 4
    assert "7 (sete) dias corridos" in results[0].text


def test_retrieves_opening_hours(retriever: PolicyRetriever) -> None:
    results = retriever.search("Qual é o horário de funcionamento no sábado?")

    assert results[0].page_number == 2
    assert "09:00 às 13:00" in results[0].text


def test_rejects_empty_query(retriever: PolicyRetriever) -> None:
    with pytest.raises(ValueError, match="não pode estar vazia"):
        retriever.search("   ")
