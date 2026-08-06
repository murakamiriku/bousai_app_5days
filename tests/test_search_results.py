import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_all_shelters_page_renders_search_results_ui(client):
    response = client.get('/all_shelters')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '避難所検索結果' in html
    assert '並び替え' in html
    assert '詳細' in html


def test_search_results_supports_sort_parameter(client):
    response = client.get('/search_results?sort=distance_asc')
    assert response.status_code == 200


def test_search_results_filters_by_crowd(client):
    response = client.get('/search_results?crowd=high')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '該当する避難所が見つかりませんでした' in html
