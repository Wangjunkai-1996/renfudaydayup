from renfu.watchlist_store import (
    list_enabled_codes,
    remove_entry,
    seed_default_if_empty,
    upsert_entry
)


def test_watchlist_seed_upsert_and_remove(tmp_path):
    db_path = tmp_path / 'signals.db'

    seed_default_if_empty(str(db_path), ['sh600079', 'sh688563'])
    assert list_enabled_codes(str(db_path)) == ['sh600079', 'sh688563']

    upsert_entry(str(db_path), code='sz000001', name='平安银行')
    assert list_enabled_codes(str(db_path)) == ['sh600079', 'sh688563', 'sz000001']

    remove_entry(str(db_path), code='sh688563')
    assert list_enabled_codes(str(db_path)) == ['sh600079', 'sz000001']

