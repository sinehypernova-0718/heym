"""Unit tests for DataTable API helpers."""

import unittest

from fastapi import HTTPException

from app.api.data_tables import _row_sort_clause


class DataTableRowSortClauseTests(unittest.TestCase):
    def test_created_at_ascending_clause(self) -> None:
        clause = _row_sort_clause("created_at", "asc")

        self.assertIn("data_table_rows.created_at ASC", str(clause))

    def test_updated_at_descending_clause(self) -> None:
        clause = _row_sort_clause("updated_at", "desc")

        self.assertIn("data_table_rows.updated_at DESC", str(clause))

    def test_unknown_sort_field_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _row_sort_clause("name", "asc")

        self.assertEqual(ctx.exception.status_code, 400)

    def test_unknown_sort_direction_raises_400(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            _row_sort_clause("created_at", "oldest")

        self.assertEqual(ctx.exception.status_code, 400)
