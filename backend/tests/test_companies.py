"""Tests for companies endpoints."""

def test_list_companies(client):
    response = client.get("/api/v1/companies")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 8  # 8 seeded companies
    symbols = [c["symbol"] for c in data]
    assert "SMPH" in symbols
    assert "BDO" in symbols
    assert "ALI" in symbols

    # Check structure
    first = data[0]
    assert "symbol" in first
    assert "name" in first
    assert "sector_name" in first
    assert "latest_close" in first


def test_list_companies_sector_filter(client):
    response = client.get("/api/v1/companies?sector=Property")
    assert response.status_code == 200
    data = response.json()
    assert len(data) > 0
    for c in data:
        assert c["sector_name"] == "Property"


def test_get_company_valid(client):
    response = client.get("/api/v1/companies/SMPH")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "SMPH"
    assert data["name"] == "SM Prime Holdings, Inc."
    assert "sector" in data
    assert data["sector"]["code"] == "PROP"
    assert "recent_prices" in data
    assert len(data["recent_prices"]) > 0
    first_price = data["recent_prices"][0]
    assert "close_price" in first_price
    assert "trade_date" in first_price


def test_get_company_case_insensitive(client):
    response = client.get("/api/v1/companies/smph")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "SMPH"


def test_get_company_invalid_symbol(client):
    response = client.get("/api/v1/companies/NONEXISTENT_XYZ")
    assert response.status_code == 404
    data = response.json()
    assert "not found" in data["detail"].lower()
