"""Exercise public application, protected review and activation against a fresh DB."""
import pytest
from fastapi.testclient import TestClient
from backend.app import database as db
from backend.app.auth_service import create_user
from backend.app.main import app


@pytest.fixture
def registration_client(tmp_path, monkeypatch):
    monkeypatch.setenv('AKI_DB_PATH', str(tmp_path / 'registration.db'))
    db.reset_initialization_cache()
    db.ensure_initialized()
    create_user(actor_id='system', username='reviewadmin', display_name='审核员',
                role='admin', password='AdminPassword123!', must_change_password=False)
    # Registration does not depend on model assets; do not run model lifespan.
    client = TestClient(app)
    yield client
    client.close()
    db.reset_initialization_cache()


def apply(client, **extra):
    return client.post('/api/auth/register', json={
        'username': 'newdoctor', 'display_name': '王医生', 'institution': '测试医院',
        'department': '肾内科', 'password': 'DoctorPassword123!', **extra,
    })


def sign_in(client, username, password):
    response = client.post('/api/auth/login', json={'username': username, 'password': password})
    if response.status_code == 200:
        client.headers['x-csrf-token'] = client.cookies.get('aki_csrf')
    return response


def test_pending_review_activation_and_permissions(registration_client):
    c = registration_client
    assert apply(c, role='admin').status_code == 422
    assert apply(c).status_code == 202
    assert apply(c, username='NEWDOCTOR').status_code == 202
    assert sign_in(c, 'newdoctor', 'DoctorPassword123!').status_code == 401
    assert c.get('/api/admin/doctor-applications').status_code == 401
    assert sign_in(c, 'reviewadmin', 'AdminPassword123!').status_code == 200
    rows = c.get('/api/admin/doctor-applications').json()['applications']
    assert len(rows) == 1 and 'password_hash' not in rows[0]
    endpoint = f"/api/admin/doctor-applications/{rows[0]['id']}/review"
    csrf = c.headers.pop('x-csrf-token')
    assert c.post(endpoint, json={'decision': 'approved'}).status_code == 403
    c.headers['x-csrf-token'] = csrf
    assert c.post(endpoint, json={'decision': 'approved'}).status_code == 200
    assert c.post(endpoint, json={'decision': 'approved'}).status_code == 409
    with db.reader() as conn:
        row = conn.execute('SELECT * FROM doctor_applications').fetchone()
        assert row['password_hash'] is None
    c.cookies.clear()
    response = sign_in(c, 'newdoctor', 'DoctorPassword123!')
    assert response.status_code == 200
    assert response.json()['user']['role'] == 'doctor'
    assert c.get('/api/admin/doctor-applications').status_code == 403
    assert c.post(endpoint, json={'decision': 'approved'}).status_code == 403


def test_rejection_validation_and_throttle(registration_client):
    c = registration_client
    assert apply(c, password='short').status_code == 422
    assert apply(c).status_code == 202
    sign_in(c, 'reviewadmin', 'AdminPassword123!')
    row = c.get('/api/admin/doctor-applications').json()['applications'][0]
    endpoint = f"/api/admin/doctor-applications/{row['id']}/review"
    assert c.post(endpoint, json={'decision': 'rejected'}).status_code == 422
    assert c.post(endpoint, json={'decision': 'rejected', 'reason': '无法核实身份'}).status_code == 200
    c.cookies.clear()
    assert sign_in(c, 'newdoctor', 'DoctorPassword123!').status_code == 401
    for i in range(4):
        assert apply(c, username=f'applicant{i}').status_code == 202
    assert apply(c, username='quotaover').status_code == 429


def test_existing_database_upgrade_preserves_users(registration_client):
    with db.transaction(immediate=True) as conn:
        conn.execute('DROP TABLE doctor_applications')
        conn.execute('PRAGMA user_version=4')
    db.reset_initialization_cache()
    db.ensure_initialized()
    with db.reader() as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 5
        assert conn.execute('SELECT count(*) FROM users').fetchone()[0] == 1
    assert apply(registration_client).status_code == 202


def test_password_whitespace_is_preserved_and_duplicate_is_not_reset(registration_client):
    c = registration_client
    password = '  PasswordWithSpaces123!  '
    assert apply(c, password=password).status_code == 202
    assert apply(c, password='ReplacementPassword123!').status_code == 202
    sign_in(c, 'reviewadmin', 'AdminPassword123!')
    row = c.get('/api/admin/doctor-applications').json()['applications'][0]
    assert c.post(f"/api/admin/doctor-applications/{row['id']}/review",
                  json={'decision': 'approved'}).status_code == 200
    c.cookies.clear()
    assert sign_in(c, 'newdoctor', password).status_code == 200
