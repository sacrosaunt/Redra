import pytest
from pydantic import ValidationError

from redra_mcp.models import SearchQuery


def test_search_query_normalizes_input():
    query = SearchQuery(keywords=["  Acme  ", "acme", "data breach"], state="ca")
    assert query.keywords == ["Acme", "data breach"]
    assert query.state == "CA"
    assert query.status == "open"


def test_search_query_rejects_invalid_state():
    with pytest.raises(ValidationError):
        SearchQuery(state="California")


def test_search_query_normalizes_and_validates_proof_requirement():
    assert SearchQuery(proof_required=" YES ").proof_required == "yes"

    with pytest.raises(ValidationError):
        SearchQuery(proof_required="sometimes")
