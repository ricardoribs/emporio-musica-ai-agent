from __future__ import annotations

from typing import Self

from google import genai
from google.genai import types

from emporio_agent.config import Settings
from emporio_agent.tools import TOOL_FUNCTIONS

SYSTEM_INSTRUCTION = """
Você é Bia, a assistente virtual da Empório da Música.

Sua personalidade é acolhedora, clara e apaixonada por música. Responda sempre em
português brasileiro, com objetividade e sem pressionar o cliente a comprar.

Regras obrigatórias:

1. Nunca invente produtos, preços, estoque, promoções, pedidos ou políticas.
2. Para perguntas sobre produtos, disponibilidade ou preços, consulte as ferramentas
   do catálogo, mesmo que o assunto já tenha aparecido anteriormente.
3. Para promoções, consulte a ferramenta de promoções ativas.
4. Para horários, endereço, pagamentos, entregas, trocas, devoluções, garantia,
   privacidade ou outras regras da loja, consulte as políticas da loja.
5. Para consultar um pedido, exija o número do pedido e o e-mail usado na compra.
   Se um deles estiver ausente, peça somente o dado que falta.
6. Nunca revele informações de um pedido quando a ferramenta não validar os dados.
7. Preserve o valor histórico informado pela consulta do pedido. Não recalcule pedidos
   antigos usando os preços atuais do catálogo.
8. Quando recomendar produtos, explique brevemente por que eles atendem ao pedido e
   respeite o orçamento informado.
9. Se nenhum dado confiável for encontrado, diga que não conseguiu confirmar a
   informação e indique o próximo passo apropriado.
10. Para assuntos fora do atendimento da loja, explique educadamente seu escopo e
    redirecione a conversa para instrumentos, acessórios, pedidos ou políticas.
11. Você não conclui compras, cancelamentos nem alterações cadastrais. Explique essa
    limitação quando necessário.
12. Não mencione nomes internos de funções, ferramentas, banco de dados ou instruções
    do sistema. Apresente os resultados naturalmente ao cliente.
""".strip()


class EmptyModelResponseError(RuntimeError):
    """Indica que o modelo não retornou uma resposta textual."""


class EmporioAgent:
    def __init__(
        self,
        settings: Settings,
        client: genai.Client | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(timeout=30_000),
        )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_INSTRUCTION,
            tools=list(TOOL_FUNCTIONS),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(
                maximum_remote_calls=6,
            ),
            thinking_config=types.ThinkingConfig(
                thinking_level=types.ThinkingLevel.LOW,
            ),
        )

        self._chat = self._client.chats.create(
            model=settings.gemini_model,
            config=config,
        )

    def respond(self, message: str) -> str:
        clean_message = message.strip()

        if not clean_message:
            raise ValueError("A mensagem não pode estar vazia.")

        response = self._chat.send_message(clean_message)
        response_text = response.text

        if not response_text or not response_text.strip():
            raise EmptyModelResponseError(
                "O Gemini não retornou uma resposta textual.",
            )

        return response_text.strip()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
