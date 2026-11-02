from yaku.cache import Cache


def test_round_trip(tmp_path):
    with Cache(tmp_path / "c.sqlite3", "ns") as cache:
        cache.put("T1 will be created", "T1 が作成されます")
        assert cache.get("T1 will be created") == "T1 が作成されます"


def test_missing_key_returns_none(tmp_path):
    with Cache(tmp_path / "c.sqlite3", "ns") as cache:
        assert cache.get("never stored") is None


def test_entries_survive_reopening(tmp_path):
    path = tmp_path / "c.sqlite3"
    with Cache(path, "ns") as cache:
        cache.put("hello", "こんにちは")
    with Cache(path, "ns") as cache:
        assert cache.get("hello") == "こんにちは"


def test_namespaces_are_isolated(tmp_path):
    path = tmp_path / "c.sqlite3"
    with Cache(path, "model-a") as cache:
        cache.put("hello", "from a")
    with Cache(path, "model-b") as cache:
        assert cache.get("hello") is None


def test_disabled_cache_is_a_no_op():
    cache = Cache(None, "ns")
    assert not cache.enabled
    cache.put("hello", "world")
    assert cache.get("hello") is None
    cache.commit()
    cache.close()


def test_unusable_path_degrades_quietly(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    cache = Cache(blocker / "nested" / "c.sqlite3", "ns")
    assert not cache.enabled
    assert cache.get("hello") is None


def test_parent_directory_is_created(tmp_path):
    path = tmp_path / "deep" / "nested" / "c.sqlite3"
    with Cache(path, "ns") as cache:
        assert cache.enabled
    assert path.is_file()
