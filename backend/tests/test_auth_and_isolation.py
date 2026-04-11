def test_admin_login_and_create_user(client):
    login_resp = client.post('/api/v1/auth/login', json={'username': 'legacy_admin', 'password': 'ChangeMe123!'})
    assert login_resp.status_code == 200
    assert login_resp.json()['user']['username'] == 'legacy_admin'

    create_resp = client.post('/api/v1/admin/users', json={'username': 'alice', 'password': 'alice123', 'role': 'user'})
    assert create_resp.status_code == 201
    assert create_resp.json()['username'] == 'alice'


def test_watchlist_isolation_between_users(client):
    admin_login = client.post('/api/v1/auth/login', json={'username': 'legacy_admin', 'password': 'ChangeMe123!'})
    assert admin_login.status_code == 200
    create_user_resp = client.post('/api/v1/admin/users', json={'username': 'bob', 'password': 'bob123', 'role': 'user'})
    assert create_user_resp.status_code == 201
    client.post('/api/v1/auth/logout')

    bob_login = client.post('/api/v1/auth/login', json={'username': 'bob', 'password': 'bob123'})
    assert bob_login.status_code == 200
    add_resp = client.post('/api/v1/watchlist', json={'symbol': 'sz300402', 'display_name': '宝色股份'})
    assert add_resp.status_code == 201

    bob_watchlist = client.get('/api/v1/market/watchlist')
    assert bob_watchlist.status_code == 200
    assert len(bob_watchlist.json()) == 1
    assert bob_watchlist.json()[0]['symbol'] == 'sz300402'

    client.post('/api/v1/auth/logout')

    admin_login_again = client.post('/api/v1/auth/login', json={'username': 'legacy_admin', 'password': 'ChangeMe123!'})
    assert admin_login_again.status_code == 200
    admin_watchlist = client.get('/api/v1/market/watchlist')
    assert admin_watchlist.status_code == 200
    payload = admin_watchlist.json()
    assert isinstance(payload, list)
    assert all(item['symbol'] != 'sz300402' for item in payload)
