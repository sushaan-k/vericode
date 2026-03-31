"""End-to-end data structure verification tests.

These tests exercise the full pipeline for data-structure-related
specifications using fake providers and backends.
"""

from __future__ import annotations

from tests.conftest import FailThenSucceedBackend, FakeBackend, FakeLLMProvider
from vericode.spec import Spec, parse_spec
from vericode.verifier import verify


class TestDataStructureVerification:
    """Pipeline tests for data structure specifications."""

    async def test_merge_sorted_lists(self) -> None:
        provider = FakeLLMProvider(
            code=(
                "def merge(a: list[int], b: list[int]) -> list[int]:\n"
                "    result = []\n"
                "    i, j = 0, 0\n"
                "    while i < len(a) and j < len(b):\n"
                "        if a[i] <= b[j]:\n"
                "            result.append(a[i])\n"
                "            i += 1\n"
                "        else:\n"
                "            result.append(b[j])\n"
                "            j += 1\n"
                "    result.extend(a[i:])\n"
                "    result.extend(b[j:])\n"
                "    return result"
            ),
            proof="theorem merge_correct := by sorry",
        )
        backend = FakeBackend(succeed=True)

        result = await verify(
            Spec(
                description="Merge two sorted lists into one sorted list",
                function_name="merge",
                input_types={"a": "List[int]", "b": "List[int]"},
                output_type="List[int]",
                preconditions=["is_sorted(a)", "is_sorted(b)"],
                postconditions=[
                    "is_sorted(result)",
                    "len(result) == len(a) + len(b)",
                    "is_permutation(result, a + b)",
                ],
            ),
            language="python",
            backend=backend,
            provider=provider,
        )

        assert result.verified is True
        assert "merge" in result.code

    async def test_insert_into_bst(self) -> None:
        provider = FakeLLMProvider(
            code=(
                "class TreeNode:\n"
                "    def __init__(self, val, left=None, right=None):\n"
                "        self.val = val\n"
                "        self.left = left\n"
                "        self.right = right\n\n"
                "def insert(root, val):\n"
                "    if root is None:\n"
                "        return TreeNode(val)\n"
                "    if val < root.val:\n"
                "        root.left = insert(root.left, val)\n"
                "    else:\n"
                "        root.right = insert(root.right, val)\n"
                "    return root"
            ),
            proof="theorem insert_preserves_bst := by sorry",
        )
        backend = FakeBackend(succeed=True)

        result = await verify(
            Spec(
                description="Insert a value into a binary search tree",
                function_name="insert",
                postconditions=["is_bst(result)"],
            ),
            backend=backend,
            provider=provider,
        )

        assert result.verified is True

    async def test_data_structure_with_refinement(self) -> None:
        """Test that a data structure proof converges after refinement."""
        provider = FakeLLMProvider()
        backend = FailThenSucceedBackend(fail_count=2)

        result = await verify(
            "Insert into a balanced BST preserving the BST invariant",
            backend=backend,
            provider=provider,
            max_iterations=5,
        )

        assert result.verified is True
        assert result.iterations == 3

    async def test_reverse_list(self) -> None:
        spec = parse_spec("Reverse a list of integers")
        assert spec.function_name == "reverse"

        provider = FakeLLMProvider(
            code="def reverse(lst: list[int]) -> list[int]:\n    return lst[::-1]",
            proof="theorem reverse_correct := by sorry",
        )
        backend = FakeBackend(succeed=True)

        result = await verify(
            spec,
            backend=backend,
            provider=provider,
        )

        assert result.verified is True
