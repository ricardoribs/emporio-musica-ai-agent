from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from textwrap import shorten

from pypdf import PdfReader
from rich.console import Console
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

from emporio_agent.config import POLICIES_PATH

console = Console()


@dataclass(frozen=True, slots=True)
class PolicyPage:
    page_number: int
    text: str


@dataclass(frozen=True, slots=True)
class PolicySearchResult:
    page_number: int
    score: float
    text: str


class PolicyRetriever:
    def __init__(self, pages: list[PolicyPage]) -> None:
        if not pages:
            raise ValueError("Nenhuma página válida foi extraída do PDF.")

        self.pages = tuple(pages)
        self.vectorizer = TfidfVectorizer(
            strip_accents="unicode",
            lowercase=True,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )
        self.document_matrix = self.vectorizer.fit_transform(page.text for page in self.pages)

    @classmethod
    def from_pdf(cls, pdf_path: Path = POLICIES_PATH) -> PolicyRetriever:
        if not pdf_path.exists():
            raise FileNotFoundError(f"Manual de políticas não encontrado: {pdf_path}")

        reader = PdfReader(pdf_path)
        pages: list[PolicyPage] = []

        for page_number, page in enumerate(reader.pages, start=1):
            text = " ".join((page.extract_text() or "").split())

            if text:
                pages.append(
                    PolicyPage(
                        page_number=page_number,
                        text=text,
                    )
                )

        return cls(pages)

    def search(
        self,
        query: str,
        top_k: int = 2,
        min_score: float = 0.01,
    ) -> list[PolicySearchResult]:
        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("A consulta de políticas não pode estar vazia.")

        if top_k < 1:
            raise ValueError("top_k deve ser maior ou igual a 1.")

        query_vector = self.vectorizer.transform([normalized_query])
        scores = linear_kernel(query_vector, self.document_matrix).ravel()
        ranking = scores.argsort()[::-1]

        results: list[PolicySearchResult] = []

        for index in ranking:
            score = float(scores[index])

            if score < min_score:
                continue

            page = self.pages[int(index)]
            results.append(
                PolicySearchResult(
                    page_number=page.page_number,
                    score=score,
                    text=page.text,
                )
            )

            if len(results) == top_k:
                break

        return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pesquisa o manual de políticas da Empório da Música."
    )
    parser.add_argument("query", nargs="+", help="Pergunta ou termos de busca.")
    parser.add_argument("--top-k", type=int, default=2)
    arguments = parser.parse_args()

    retriever = PolicyRetriever.from_pdf()
    results = retriever.search(
        query=" ".join(arguments.query),
        top_k=arguments.top_k,
    )

    if not results:
        console.print("[yellow]Nenhuma política relevante encontrada.[/yellow]")
        return

    for result in results:
        console.rule(f"Página {result.page_number} — relevância {result.score:.3f}")
        console.print(shorten(result.text, width=800, placeholder="..."))


if __name__ == "__main__":
    main()
