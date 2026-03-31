"""Tests for the verification cache module."""

from __future__ import annotations

from pathlib import Path

from vericode.cache import CacheEntry, VerificationCache, cache_key
from vericode.spec import Spec

# ---------------------------------------------------------------------------
# cache_key tests
# ---------------------------------------------------------------------------


class TestCacheKey:
    """Tests for the ``cache_key`` function."""

    def test_deterministic(self) -> None:
        """Same inputs always produce the same key."""
        spec = Spec(description="Sort a list", function_name="sort")
        k1 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 == k2

    def test_different_backend_different_key(self) -> None:
        spec = Spec(description="Sort a list", function_name="sort")
        k1 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec,
            "dafny",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 != k2

    def test_different_provider_different_key(self) -> None:
        spec = Spec(description="Sort a list", function_name="sort")
        k1 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec,
            "lean4",
            "openai",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 != k2

    def test_different_spec_different_key(self) -> None:
        spec_a = Spec(description="Sort a list", function_name="sort")
        spec_b = Spec(description="Search a list", function_name="search")
        k1 = cache_key(
            spec_a,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec_b,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 != k2

    def test_key_is_64_hex_chars(self) -> None:
        spec = Spec(description="Sort a list")
        key = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_case_insensitive_backend_and_provider(self) -> None:
        spec = Spec(description="Sort a list")
        k1 = cache_key(
            spec,
            "LEAN4",
            "Anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 == k2

    def test_different_language_different_key(self) -> None:
        spec = Spec(description="Sort a list", function_name="sort")
        k1 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="rust",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 != k2

    def test_different_existing_code_different_key(self) -> None:
        spec = Spec(description="Sort a list", function_name="sort")
        k1 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            existing_code="def sort(xs): return xs",
            temperature=0.2,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            existing_code="def sort(xs): return sorted(xs)",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 != k2

    def test_different_temperature_different_key(self) -> None:
        spec = Spec(description="Sort a list", function_name="sort")
        k1 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.1,
            max_tokens=4096,
        )
        k2 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.9,
            max_tokens=4096,
        )
        assert k1 != k2

    def test_different_max_tokens_different_key(self) -> None:
        spec = Spec(description="Sort a list", function_name="sort")
        k1 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=2048,
        )
        k2 = cache_key(
            spec,
            "lean4",
            "anthropic",
            language="python",
            temperature=0.2,
            max_tokens=4096,
        )
        assert k1 != k2


# ---------------------------------------------------------------------------
# VerificationCache tests
# ---------------------------------------------------------------------------


class TestVerificationCache:
    """Tests for ``VerificationCache`` get/put/clear."""

    def test_miss_returns_none(self, tmp_path: Path) -> None:
        vc = VerificationCache(cache_dir=tmp_path / "cache")
        assert vc.get("nonexistent") is None

    def test_round_trip(self, tmp_path: Path) -> None:
        vc = VerificationCache(cache_dir=tmp_path / "cache")
        entry = CacheEntry(
            cache_key="abc123",
            code="def sort(lst): return sorted(lst)",
            proof="theorem sort_correct := by sorry",
            backend="lean4",
            language="python",
            certificate_json='{"verified": true}',
        )
        vc.put(entry)
        result = vc.get("abc123")

        assert result is not None
        assert result.code == entry.code
        assert result.proof == entry.proof
        assert result.backend == "lean4"
        assert result.language == "python"

    def test_clear(self, tmp_path: Path) -> None:
        vc = VerificationCache(cache_dir=tmp_path / "cache")
        for i in range(3):
            entry = CacheEntry(
                cache_key=f"key{i}",
                code=f"code{i}",
                proof=f"proof{i}",
                backend="lean4",
                language="python",
                certificate_json="{}",
            )
            vc.put(entry)

        removed = vc.clear()
        assert removed == 3
        assert vc.get("key0") is None

    def test_clear_empty_cache(self, tmp_path: Path) -> None:
        vc = VerificationCache(cache_dir=tmp_path / "cache")
        assert vc.clear() == 0

    def test_corrupt_entry_returns_none(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "bad.json").write_text("not valid json{{{")

        vc = VerificationCache(cache_dir=cache_dir)
        assert vc.get("bad") is None

    def test_cache_dir_created_on_put(self, tmp_path: Path) -> None:
        cache_dir = tmp_path / "nested" / "cache" / "dir"
        vc = VerificationCache(cache_dir=cache_dir)
        entry = CacheEntry(
            cache_key="test",
            code="code",
            proof="proof",
            backend="lean4",
            language="python",
            certificate_json="{}",
        )
        vc.put(entry)
        assert cache_dir.exists()
        assert (cache_dir / "test.json").exists()


# ---------------------------------------------------------------------------
# Integration with verify pipeline
# ---------------------------------------------------------------------------


class TestCacheIntegration:
    """Test that verify() uses the cache end-to-end."""

    async def test_cached_result_skips_pipeline(self, tmp_path: Path) -> None:
        """A cached result should be returned without calling the LLM."""
        from tests.conftest import FakeBackend, FakeLLMProvider
        from vericode.cache import VerificationCache
        from vericode.verifier import verify

        spec = Spec(description="Sort a list", function_name="sort")
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)

        cache_dir = tmp_path / "cache"
        vc = VerificationCache(cache_dir=cache_dir)

        # First call: populates cache
        result1 = await verify(
            spec,
            backend=backend,
            provider=provider,
            cache=vc,
        )
        assert result1.verified is True
        assert provider.call_count == 1

        # Second call: should use cache, no extra LLM call
        result2 = await verify(
            spec,
            backend=backend,
            provider=provider,
            cache=vc,
        )
        assert result2.verified is True
        assert result2.iterations == 0  # cache hit indicator
        assert provider.call_count == 1  # no new LLM call

    async def test_no_cache_flag_skips_cache(self, tmp_path: Path) -> None:
        """When use_cache=False, the cache should not be consulted."""
        from tests.conftest import FakeBackend, FakeLLMProvider
        from vericode.cache import VerificationCache
        from vericode.verifier import verify

        spec = Spec(description="Sort a list", function_name="sort")
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)

        cache_dir = tmp_path / "cache"
        vc = VerificationCache(cache_dir=cache_dir)

        # First call with cache
        await verify(spec, backend=backend, provider=provider, cache=vc)
        assert provider.call_count == 1

        # Second call with use_cache=False
        result = await verify(
            spec,
            backend=backend,
            provider=provider,
            cache=vc,
            use_cache=False,
        )
        assert result.verified is True
        assert provider.call_count == 2  # LLM was called again

    async def test_existing_code_uses_distinct_cache_entries(
        self, tmp_path: Path
    ) -> None:
        """Different user-supplied implementations must not share cache hits."""
        from tests.conftest import FakeBackend, FakeLLMProvider
        from vericode.cache import VerificationCache
        from vericode.verifier import verify

        spec = Spec(description="Sort a list", function_name="sort")
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)
        vc = VerificationCache(cache_dir=tmp_path / "cache")

        result_one = await verify(
            spec,
            backend=backend,
            provider=provider,
            cache=vc,
            existing_code="def sort(xs): return xs",
        )
        result_two = await verify(
            spec,
            backend=backend,
            provider=provider,
            cache=vc,
            existing_code="def sort(xs): return sorted(xs)",
        )

        assert result_one.verified is True
        assert result_two.verified is True
        assert provider.call_count == 2

    async def test_generation_settings_use_distinct_cache_entries(
        self, tmp_path: Path
    ) -> None:
        """Different generation settings must not share cached artifacts."""
        from tests.conftest import FakeBackend, FakeLLMProvider
        from vericode.cache import VerificationCache
        from vericode.verifier import verify

        spec = Spec(description="Sort a list", function_name="sort")
        provider = FakeLLMProvider()
        backend = FakeBackend(succeed=True)
        vc = VerificationCache(cache_dir=tmp_path / "cache")

        first = await verify(
            spec,
            backend=backend,
            provider=provider,
            cache=vc,
            temperature=0.1,
            max_tokens=2048,
        )
        second = await verify(
            spec,
            backend=backend,
            provider=provider,
            cache=vc,
            temperature=0.7,
            max_tokens=4096,
        )

        assert first.verified is True
        assert second.verified is True
        assert provider.call_count == 2
