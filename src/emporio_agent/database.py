from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from rich.console import Console

from emporio_agent.config import DATA_DIR, DATABASE_PATH

console = Console()

LOAD_ORDER = (
    "categories",
    "customers",
    "products",
    "orders",
    "order_items",
    "promotions",
)

SCHEMA = """
DROP TABLE IF EXISTS order_items;
DROP TABLE IF EXISTS promotions;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS products;
DROP TABLE IF EXISTS customers;
DROP TABLE IF EXISTS categories;

CREATE TABLE categories (
    category_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE customers (
    customer_id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    email TEXT NOT NULL,
    city TEXT NOT NULL
);

CREATE TABLE products (
    product_id INTEGER PRIMARY KEY,
    price_brl REAL NOT NULL CHECK (price_brl >= 0),
    name TEXT NOT NULL,
    category_id INTEGER NOT NULL,
    description TEXT NOT NULL,
    stock_quantity INTEGER NOT NULL CHECK (stock_quantity >= 0),
    status TEXT NOT NULL,
    specs TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (category_id) REFERENCES categories(category_id)
);

CREATE TABLE orders (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TEXT NOT NULL,
    status TEXT NOT NULL,
    total_brl REAL NOT NULL CHECK (total_brl >= 0),
    payment_method TEXT NOT NULL,
    tracking_code TEXT,
    estimated_delivery TEXT,
    notes TEXT,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    order_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    product_id INTEGER NOT NULL,
    PRIMARY KEY (order_id, product_id),
    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);

CREATE TABLE promotions (
    promotion_id INTEGER PRIMARY KEY,
    product_id INTEGER NOT NULL,
    discount_percent REAL NOT NULL CHECK (
        discount_percent >= 0 AND discount_percent <= 100
    ),
    description TEXT NOT NULL,
    is_active INTEGER NOT NULL CHECK (is_active IN (0, 1)),
    FOREIGN KEY (product_id) REFERENCES products(product_id)
);
"""


def find_csv(data_dir: Path, table_name: str) -> Path:
    matches = list(data_dir.glob(f"* - {table_name}.csv"))

    if len(matches) != 1:
        raise FileNotFoundError(
            f"Esperado um CSV para '{table_name}', encontrados: {len(matches)}."
        )

    return matches[0]


def insert_csv(
    connection: sqlite3.Connection,
    table_name: str,
    csv_path: Path,
) -> int:
    with csv_path.open(encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)

        if not reader.fieldnames:
            raise ValueError(f"O CSV está sem cabeçalho: {csv_path.name}")

        columns = tuple(reader.fieldnames)
        rows = [
            tuple(row[column] if row[column] != "" else None for column in columns)
            for row in reader
        ]

    quoted_columns = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)

    connection.executemany(
        f'INSERT INTO "{table_name}" ({quoted_columns}) VALUES ({placeholders})',
        rows,
    )

    return len(rows)


def build_database(
    data_dir: Path = DATA_DIR,
    database_path: Path = DATABASE_PATH,
) -> dict[str, int]:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(SCHEMA)

        for table_name in LOAD_ORDER:
            csv_path = find_csv(data_dir, table_name)
            counts[table_name] = insert_csv(connection, table_name, csv_path)

        violations = connection.execute("PRAGMA foreign_key_check").fetchall()

        if violations:
            raise sqlite3.IntegrityError(
                f"Foram encontradas violações de chave estrangeira: {violations}"
            )

    return counts


def connect_database(
    database_path: Path = DATABASE_PATH,
) -> sqlite3.Connection:
    if not database_path.exists():
        raise FileNotFoundError("Banco não encontrado. Execute `python -m emporio_agent.database`.")

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def main() -> None:
    try:
        counts = build_database()
    except (FileNotFoundError, ValueError, sqlite3.Error) as error:
        console.print(f"[bold red]Erro ao construir o banco:[/bold red] {error}")
        raise SystemExit(1) from error

    console.print("[bold green]Banco criado com sucesso.[/bold green]")

    for table_name, row_count in counts.items():
        console.print(f"- {table_name}: {row_count} registros")

    console.print(f"Arquivo local: {DATABASE_PATH}")


if __name__ == "__main__":
    main()
