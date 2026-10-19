from unittest.mock import Mock
import semantic_cache


def test_disabled_cache_never_calls_embedding_service(monkeypatch):
    monkeypatch.setattr(semantic_cache, 'CACHE_ENABLED', False)
    embedding = Mock(side_effect=AssertionError('Unexpected embedding request'))
    monkeypatch.setattr(semantic_cache, 'get_embedding', embedding)
    assert semantic_cache.check_cache('hours') is None
    semantic_cache.store_in_cache('hours', 'Nine to six', False)
    embedding.assert_not_called()


def test_enabled_cache_remains_clinic_scoped(monkeypatch):
    monkeypatch.setattr(semantic_cache, 'CACHE_ENABLED', True)
    monkeypatch.setattr(semantic_cache, '_cache', [])
    monkeypatch.setattr(semantic_cache, 'get_embedding', lambda _: [1, 0])
    semantic_cache.store_in_cache('hours', 'Nine to six', False, 'default')
    assert semantic_cache.check_cache('hours', 'default')['response'] == 'Nine to six'
    assert semantic_cache.check_cache('hours', 'smilecare') is None
