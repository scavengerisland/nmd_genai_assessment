"""Tests for preprocess helpers."""

import pytest

from tasks.preprocess import document_id_from_key


@pytest.mark.parametrize(
    ("key", "expected"),
    [("uploads/a.json", "a"), ("uploads/nested/b.json", "b"), ("uploads/my.json.notes.json", "my.json.notes")],
)
def test_document_id_strips_only_the_trailing_suffix(key, expected):
    assert document_id_from_key(key) == expected
