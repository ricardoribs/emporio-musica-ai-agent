import pytest

from emporio_agent.database import build_database
from emporio_agent.tools import (
    get_active_promotions,
    get_order_status,
    get_product_details,
    search_products,
    search_store_policies,
)


@pytest.fixture(scope="module", autouse=True)
def prepared_database() -> None:
    build_database()


def test_searches_available_guitars_with_budget() -> None:
    result = search_products(
        category="violões",
        max_price=1000,
        limit=20,
    )

    assert result["count"] == 12
    assert all(
        product["available"] and product["effective_price_brl"] <= 1000
        for product in result["products"]
    )


def test_gets_specific_product_details() -> None:
    result = get_product_details("Takamine GD20")

    assert result["found"] is True
    assert result["product"]["original_price_brl"] == 2199.0
    assert result["product"]["stock_quantity"] == 5


def test_lists_active_promotions() -> None:
    result = get_active_promotions()

    assert result["count"] == 4
    assert all(product["promotion"] is not None for product in result["promotions"])


def test_rejects_order_with_wrong_email() -> None:
    result = get_order_status(
        order_id=1,
        customer_email="email-incorreto@example.com",
    )

    assert result["verified"] is False
    assert "validar" in result["message"]


def test_returns_order_after_identity_validation() -> None:
    result = get_order_status(
        order_id=1,
        customer_email="pedro.oliveira@jmail.com",
    )

    assert result["verified"] is True
    assert result["order"]["status"] == "entregue"
    assert result["order"]["total_brl"] == 11499.0


def test_searches_store_policies() -> None:
    result = search_store_policies("direito de arrependimento em compra online")

    assert result["results"][0]["page"] == 4
    assert "7 (sete) dias corridos" in result["results"][0]["content"]
