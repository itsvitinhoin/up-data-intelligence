"""Encode offline results for a future NUMERIC writer; never persist anything."""

from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Any

from src.analytics.schema import SCHEMAS
from src.utils.data import numeric


def encode_tables(tables: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    encoded = {}
    for table, rows in tables.items():
        fields = SCHEMAS[table].fields
        output = []
        for row in rows:
            if set(row) != set(fields):
                raise ValueError("analytics_schema_mismatch")
            record = dict(row)
            for key, value in record.items():
                if fields[key] == "NUMERIC" and value is not None:
                    with localcontext() as context:
                        context.prec = 78
                        rounded = Decimal(str(value)).quantize(
                            Decimal("0.000000001"), rounding=ROUND_HALF_UP
                        )
                        record[key] = numeric(rounded)
            output.append(record)
        encoded[table] = output
    return encoded
