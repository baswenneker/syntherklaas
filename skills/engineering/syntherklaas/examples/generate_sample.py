"""Generate the demo input — both ``example_data/xlsx/example_data.xlsx`` and ``example_data/csv/*.csv``.

The data is itself already fake (Faker output) but it serves as realistic
input for the pipeline to detect and re-anonymize. The ``_pii_config`` sheet
forces PII types so the round trip works without depending on Presidio's
auto-detection of these column types.
"""

from __future__ import annotations

import random
import string
from pathlib import Path

import pandas as pd
from faker import Faker

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parents[3]
EXCEL_PATH = PROJECT_ROOT / "example_data" / "xlsx" / "example_data.xlsx"
CSV_DIR = PROJECT_ROOT / "example_data" / "csv"


def _gen_postcode(rng: random.Random) -> str:
    digits = f"{rng.randint(1000, 9999)}"
    letters = "".join(rng.choice(string.ascii_uppercase) for _ in range(2))
    return f"{digits} {letters}"


def main() -> None:
    Faker.seed(42)
    fake = Faker(["nl_NL"])
    rng = random.Random(42)

    n_klanten = 50
    klanten = pd.DataFrame(
        {
            "id": list(range(1, n_klanten + 1)),
            "naam": [fake.name() for _ in range(n_klanten)],
            "email": [fake.email() for _ in range(n_klanten)],
            "bsn": [f"{rng.randint(100000000, 999999999)}" for _ in range(n_klanten)],
            "telefoon": [
                f"06-{rng.randint(10000000, 99999999)}" for _ in range(n_klanten)
            ],
            "postcode": [_gen_postcode(rng) for _ in range(n_klanten)],
        }
    )

    orders_rows = []
    next_order = 1
    for klant_id in klanten["id"]:
        for _ in range(rng.randint(0, 8)):
            orders_rows.append(
                {"id": next_order, "klant_id": int(klant_id), "datum": "2024-01-01"}
            )
            next_order += 1
    orders = pd.DataFrame(orders_rows)

    orderlines_rows = []
    next_line = 1
    products = ("Widget A", "Widget B", "Gadget X", "Gizmo Y")
    for oid in orders["id"]:
        for _ in range(rng.randint(1, 5)):
            orderlines_rows.append(
                {
                    "id": next_line,
                    "order_id": int(oid),
                    "product": rng.choice(products),
                    "prijs": round(rng.uniform(10, 200), 2),
                }
            )
            next_line += 1
    orderlines = pd.DataFrame(orderlines_rows)

    relations = pd.DataFrame(
        {
            "table": ["orders", "orderlines"],
            "column": ["klant_id", "order_id"],
            "references_table": ["klanten", "orders"],
            "references_column": ["id", "id"],
        }
    )

    pii_config = pd.DataFrame(
        {
            "table": ["klanten"] * 5 + ["orders", "orderlines"],
            "column": ["naam", "email", "bsn", "telefoon", "postcode", "datum", "product"],
            "pii_type": [
                "PERSON",
                "EMAIL_ADDRESS",
                "BSN",
                "NL_PHONE",
                "NL_POSTCODE",
                "NONE",
                "NONE",
            ],
            "strategy": ["force"] * 5 + ["skip", "skip"],
        }
    )

    EXCEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(EXCEL_PATH, engine="openpyxl") as writer:
        klanten.to_excel(writer, sheet_name="klanten", index=False)
        orders.to_excel(writer, sheet_name="orders", index=False)
        orderlines.to_excel(writer, sheet_name="orderlines", index=False)
        relations.to_excel(writer, sheet_name="_relations", index=False)
        pii_config.to_excel(writer, sheet_name="_pii_config", index=False)
    print(
        f"Wrote {EXCEL_PATH} "
        f"({n_klanten} klanten, {len(orders)} orders, {len(orderlines)} orderlines)"
    )

    CSV_DIR.mkdir(parents=True, exist_ok=True)
    klanten.to_csv(CSV_DIR / "klanten.csv", index=False)
    orders.to_csv(CSV_DIR / "orders.csv", index=False)
    orderlines.to_csv(CSV_DIR / "orderlines.csv", index=False)
    relations.to_csv(CSV_DIR / "_relations.csv", index=False)
    pii_config.to_csv(CSV_DIR / "_pii_config.csv", index=False)
    print(f"Wrote {CSV_DIR}/ (5 CSV files)")


if __name__ == "__main__":
    main()
