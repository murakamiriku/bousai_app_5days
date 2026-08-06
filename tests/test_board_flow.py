import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app, instructions


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_board_index_renders_lists(client):
    response = client.get('/board')
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert '庁内向け指示一覧' in html
    assert '住民向け発信一覧' in html


def test_internal_form_accepts_draft(client):
    initial_len = len(instructions)
    response = client.post('/board/internal/new', data={
        'title': 'テスト件名',
        'content': 'テスト内容',
        'submit_action': 'draft',
    }, follow_redirects=True)
    assert response.status_code == 200
    assert len(instructions) == initial_len + 1


def test_resident_form_accepts_publish(client):
    response = client.post('/board/resident/new', data={
        'title': 'テスト発信',
        'content': 'テスト発信内容',
        'submit_action': 'submit',
    }, follow_redirects=True)
    assert response.status_code == 200
