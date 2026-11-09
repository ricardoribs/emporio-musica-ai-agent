from __future__ import annotations

import json
from difflib import SequenceMatcher
from functools import lru_cache
from sqlite3 import Row
from unicodedata import normalize as unicode_normalize

from emporio_agent.database import connect_database
from emporio_agent.policy_retriever import PolicyRetriever

STATUS_LABELS = {
    "pending": "pendente",
    "confirmed": "confirmado",
    "shipped": "enviado",
    "delivered": "entregue",
    "cancelled": "cancelado",
}


def normalize_text(value: str) -> str:
    normalized = unicode_normalize("NFKD", value)
    return normalized.encode("ascii", "ignore").decode("ascii").casefold()


def text_matches(query: str, text: str) -> bool:
    normalized_query = normalize_text(query)
    normalized_text = normalize_text(text)

    if normalized_query in normalized_text:
        return True

    return SequenceMatcher(None, normalized_query, normalized_text).ratio() >= 0.72


def load_product_rows() -> list[Row]:
    with connect_database() as connection:
        return connection.execute(
            """
            SELECT
                p.product_id,
                p.name,
                p.description,
                p.price_brl,
                p.stock_quantity,
                p.status,
                p.specs,
                c.name AS category_name,
                pr.description AS promotion_description,
                pr.discount_percent
            FROM products AS p
            JOIN categories AS c
                ON c.category_id = p.category_id
            LEFT JOIN promotions AS pr
                ON pr.product_id = p.product_id
                AND pr.is_active = 1
            """
        ).fetchall()


def serialize_product(row: Row) -> dict[str, object]:
    original_price = round(float(row["price_brl"]), 2)
    discount = row["discount_percent"]
    promotion = None
    effective_price = original_price

    if discount is not None:
        discount = float(discount)
        effective_price = round(original_price * (1 - discount / 100), 2)
        promotion = {
            "description": row["promotion_description"],
            "discount_percent": discount,
            "promotional_price_brl": effective_price,
        }

    return {
        "product_id": int(row["product_id"]),
        "name": row["name"],
        "category": row["category_name"],
        "description": row["description"],
        "original_price_brl": original_price,
        "effective_price_brl": effective_price,
        "stock_quantity": int(row["stock_quantity"]),
        "status": row["status"],
        "available": row["status"] == "active" and row["stock_quantity"] > 0,
        "promotion": promotion,
    }


def search_products(
    query: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    available_only: bool = True,
    limit: int = 5,
) -> dict[str, object]:
    """Busca produtos por nome, descrição, categoria, preço e disponibilidade.

    Use quando o cliente procurar opções de instrumentos ou informar um orçamento.
    O preço máximo considera o preço promocional quando existir promoção ativa.
    """
    if max_price is not None and max_price < 0:
        raise ValueError("max_price não pode ser negativo.")

    if limit < 1 or limit > 20:
        raise ValueError("limit deve estar entre 1 e 20.")

    products: list[dict[str, object]] = []

    for row in load_product_rows():
        searchable_text = " ".join(
            (
                row["name"],
                row["description"],
                row["category_name"],
            )
        )

        if query and not text_matches(query, searchable_text):
            continue

        if category and not text_matches(category, row["category_name"]):
            continue

        product = serialize_product(row)

        if available_only and not product["available"]:
            continue

        if max_price is not None and float(product["effective_price_brl"]) > max_price:
            continue

        products.append(product)

    products.sort(
        key=lambda product: (
            float(product["effective_price_brl"]),
            str(product["name"]),
        )
    )

    limited_products = products[:limit]

    return {
        "count": len(limited_products),
        "products": limited_products,
    }


def get_product_details(product_name: str) -> dict[str, object]:
    """Retorna preço, estoque, especificações e promoção de um produto.

    Use quando o cliente perguntar por um modelo específico.
    """
    normalized_query = normalize_text(product_name)

    if not normalized_query:
        raise ValueError("product_name não pode estar vazio.")

    rows = load_product_rows()

    def similarity(row: Row) -> float:
        normalized_name = normalize_text(row["name"])

        if normalized_query == normalized_name:
            return 1.0

        if normalized_query in normalized_name:
            return 0.95

        return SequenceMatcher(
            None,
            normalized_query,
            normalized_name,
        ).ratio()

    best_match = max(rows, key=similarity)
    best_score = similarity(best_match)

    if best_score < 0.45:
        return {
            "found": False,
            "message": "Produto não encontrado no catálogo.",
        }

    product = serialize_product(best_match)
    product["specs"] = json.loads(best_match["specs"])

    alternatives: list[dict[str, object]] = []

    if not product["available"]:
        search_result = search_products(
            category=str(product["category"]),
            available_only=True,
            limit=4,
        )
        alternatives = [
            alternative
            for alternative in search_result["products"]
            if alternative["product_id"] != product["product_id"]
        ][:3]

    return {
        "found": True,
        "match_score": round(best_score, 3),
        "product": product,
        "alternatives": alternatives,
    }


def get_active_promotions(limit: int = 10) -> dict[str, object]:
    """Lista promoções atualmente ativas e seus preços finais."""
    if limit < 1 or limit > 20:
        raise ValueError("limit deve estar entre 1 e 20.")

    products = [
        serialize_product(row) for row in load_product_rows() if row["discount_percent"] is not None
    ]

    products.sort(
        key=lambda product: (
            -float(product["promotion"]["discount_percent"]),
            str(product["name"]),
        )
    )

    return {
        "count": min(len(products), limit),
        "promotions": products[:limit],
    }


def get_order_status(
    order_id: int,
    customer_email: str,
) -> dict[str, object]:
    """Consulta um pedido após validar o número e o e-mail do cliente.

    Nunca use somente o número do pedido. Solicite também o e-mail da compra.
    """
    if order_id < 1 or not customer_email.strip():
        return {
            "verified": False,
            "message": "Não foi possível validar os dados do pedido.",
        }

    with connect_database() as connection:
        order = connection.execute(
            """
            SELECT
                o.order_id,
                o.order_date,
                o.status,
                o.total_brl,
                o.payment_method,
                o.tracking_code,
                o.estimated_delivery,
                o.notes,
                c.name AS customer_name
            FROM orders AS o
            JOIN customers AS c
                ON c.customer_id = o.customer_id
            WHERE o.order_id = ?
                AND LOWER(c.email) = LOWER(?)
            """,
            (order_id, customer_email.strip()),
        ).fetchone()

        if order is None:
            return {
                "verified": False,
                "message": "Não foi possível validar os dados do pedido.",
            }

        items = connection.execute(
            """
            SELECT p.name, oi.quantity
            FROM order_items AS oi
            JOIN products AS p
                ON p.product_id = oi.product_id
            WHERE oi.order_id = ?
            ORDER BY p.name
            """,
            (order_id,),
        ).fetchall()

    return {
        "verified": True,
        "order": {
            "order_id": int(order["order_id"]),
            "customer_first_name": order["customer_name"].split()[0],
            "order_date": order["order_date"],
            "status": STATUS_LABELS.get(order["status"], order["status"]),
            "total_brl": round(float(order["total_brl"]), 2),
            "payment_method": order["payment_method"],
            "tracking_code": order["tracking_code"],
            "estimated_delivery": order["estimated_delivery"],
            "notes": order["notes"],
            "items": [
                {
                    "name": item["name"],
                    "quantity": int(item["quantity"]),
                }
                for item in items
            ],
        },
    }


@lru_cache(maxsize=1)
def get_policy_retriever() -> PolicyRetriever:
    return PolicyRetriever.from_pdf()


def search_store_policies(
    query: str,
    top_k: int = 2,
) -> dict[str, object]:
    """Busca regras, horários, endereço, pagamentos, trocas e garantias.

    Use para perguntas cuja resposta esteja no manual de políticas da loja.
    """
    if top_k < 1 or top_k > 3:
        raise ValueError("top_k deve estar entre 1 e 3.")

    results = get_policy_retriever().search(
        query=query,
        top_k=top_k,
    )

    return {
        "query": query,
        "results": [
            {
                "page": result.page_number,
                "relevance": round(result.score, 4),
                "content": result.text,
            }
            for result in results
        ],
    }


TOOL_FUNCTIONS = (
    search_products,
    get_product_details,
    get_active_promotions,
    get_order_status,
    search_store_policies,
)
