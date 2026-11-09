import sqlite3

from emporio_agent.config import DATA_DIR
from emporio_agent.database import build_database


def test_build_database(tmp_path) -> None:
    database_path = tmp_path / "store.db"

    counts = build_database(
        data_dir=DATA_DIR,
        database_path=database_path,
    )

    assert counts == {
        "categories": 9,
        "customers": 50,
        "products": 65,
        "orders": 20,
        "order_items": 22,
        "promotions": 25,
    }

    with sqlite3.connect(database_path) as connection:
        violations = connection.execute("PRAGMA foreign_key_check").fetchall()

        product = connection.execute(
            """
            SELECT price_brl, stock_quantity, status
            FROM products
            WHERE name = ?
            """,
            ("Takamine GD20 Dreadnought Natural",),
        ).fetchone()

    assert violations == []
    assert product == (2199.0, 5, "active")
