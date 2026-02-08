import pytest


@pytest.fixture
def grafana_response_sample() -> dict:
    """Sample Grafana API response for testing."""
    return {
        "results": {
            "A": {
                "frames": [
                    {
                        "schema": {
                            "name": "test",
                            "fields": [
                                {"name": "time", "type": "time"},
                                {"name": "value", "type": "number"},
                            ],
                        },
                        "data": {
                            "values": [
                                [1700000000000, 1700000060000],
                                [42.0, 43.0],
                            ]
                        },
                    }
                ]
            }
        }
    }
