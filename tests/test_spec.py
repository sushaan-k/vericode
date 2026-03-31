"""Tests for the spec parsing module."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from vericode.exceptions import SpecParsingError
from vericode.spec import Spec, load_spec_from_yaml, parse_spec

# ---------------------------------------------------------------------------
# Spec model tests
# ---------------------------------------------------------------------------


class TestSpec:
    """Tests for the ``Spec`` Pydantic model."""

    def test_minimal_spec(self) -> None:
        """A Spec needs only a description."""
        spec = Spec(description="Sort a list")
        assert spec.description == "Sort a list"
        assert spec.function_name == "sort"

    def test_explicit_fields(self) -> None:
        """All fields can be set explicitly."""
        spec = Spec(
            description="Merge two sorted lists",
            function_name="merge",
            input_types={"a": "List[int]", "b": "List[int]"},
            output_type="List[int]",
            preconditions=["is_sorted(a)", "is_sorted(b)"],
            postconditions=["is_sorted(result)"],
            invariants=["len(merged) <= len(a) + len(b)"],
            edge_cases=["a == []", "b == []"],
        )
        assert spec.function_name == "merge"
        assert len(spec.preconditions) == 2
        assert len(spec.postconditions) == 1
        assert len(spec.edge_cases) == 2

    def test_function_name_inference_sort(self) -> None:
        spec = Spec(description="Sort a list of integers")
        assert spec.function_name == "sort"

    def test_function_name_inference_binary_search(self) -> None:
        spec = Spec(description="Perform a binary search on an array")
        assert spec.function_name == "binary_search"

    def test_function_name_inference_merge(self) -> None:
        spec = Spec(description="Merge two lists")
        assert spec.function_name == "merge"

    def test_function_name_inference_fallback(self) -> None:
        spec = Spec(description="do something custom")
        assert spec.function_name  # should pick some name, not crash

    def test_explicit_name_not_overridden(self) -> None:
        spec = Spec(description="Sort a list", function_name="my_sort")
        assert spec.function_name == "my_sort"

    def test_empty_defaults(self) -> None:
        spec = Spec(description="test")
        assert spec.input_types == {}
        assert spec.output_type == ""
        assert spec.preconditions == []
        assert spec.postconditions == []
        assert spec.invariants == []
        assert spec.edge_cases == []


# ---------------------------------------------------------------------------
# Complexity scoring tests
# ---------------------------------------------------------------------------


class TestComplexityScore:
    """Tests for ``Spec.complexity_score()``."""

    def test_minimal_spec_low_score(self) -> None:
        """A bare-bones spec should have a very low complexity score."""
        spec = Spec(description="Sort a list")
        score = spec.complexity_score()
        assert 0.0 <= score <= 0.15

    def test_rich_spec_higher_score(self) -> None:
        """A spec with many constraints should score higher."""
        spec = Spec(
            description="Merge two sorted lists into one sorted list " * 10,
            postconditions=[
                "is_sorted(result)",
                "len(result) == len(a) + len(b)",
                "is_permutation(result, a + b)",
            ],
            edge_cases=["a == []", "b == []", "len(a) == 1"],
            preconditions=["is_sorted(a)", "is_sorted(b)"],
            invariants=["len(merged) <= len(a) + len(b)"],
        )
        score = spec.complexity_score()
        assert score > 0.5

    def test_score_bounded_zero_to_one(self) -> None:
        """Even an extreme spec must return a score in [0, 1]."""
        spec = Spec(
            description="x" * 2000,
            postconditions=[f"p{i}" for i in range(20)],
            edge_cases=[f"e{i}" for i in range(20)],
            preconditions=[f"pre{i}" for i in range(20)],
            invariants=[f"inv{i}" for i in range(20)],
        )
        score = spec.complexity_score()
        assert score == 1.0

    def test_empty_description_zero_desc_component(self) -> None:
        """Description component should be zero for a very short description."""
        spec = Spec(description="x")
        score = spec.complexity_score()
        # Only desc contributes and it's ~0.002 / 500 -> tiny
        assert score < 0.01

    def test_postconditions_are_dominant_factor(self) -> None:
        """Postconditions have the highest weight (0.35)."""
        base = Spec(description="Sort a list")
        with_post = Spec(
            description="Sort a list",
            postconditions=["is_sorted(result)", "is_permutation(result, input)"],
        )
        assert with_post.complexity_score() > base.complexity_score()


# ---------------------------------------------------------------------------
# parse_spec tests
# ---------------------------------------------------------------------------


class TestParseSpec:
    """Tests for the ``parse_spec`` function."""

    def test_basic_sort_spec(self) -> None:
        spec = parse_spec("Sort a list of integers")
        assert spec.function_name == "sort"
        assert spec.description == "Sort a list of integers"

    def test_extracts_sorted_postcondition(self) -> None:
        spec = parse_spec("Sort a list, output must be sorted")
        assert any("sorted" in p.lower() for p in spec.postconditions)

    def test_extracts_permutation_postcondition(self) -> None:
        spec = parse_spec("Output must be a permutation of input")
        assert any("permutation" in p.lower() for p in spec.postconditions)

    def test_extracts_empty_edge_case(self) -> None:
        spec = parse_spec("Handle empty lists when sorting")
        assert any("empty" in e.lower() or "[]" in e for e in spec.edge_cases)

    def test_empty_string_raises(self) -> None:
        with pytest.raises(SpecParsingError, match="empty"):
            parse_spec("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(SpecParsingError, match="empty"):
            parse_spec("   \n\t  ")

    @pytest.mark.parametrize(
        "text,expected_name",
        [
            ("find the maximum element", "find"),
            ("search for a value in a sorted array", "search"),
            ("reverse a linked list", "reverse"),
            ("compute the factorial of n", "compute"),
            ("filter even numbers from a list", "filter"),
            ("count the occurrences", "count"),
        ],
    )
    def test_various_function_names(self, text: str, expected_name: str) -> None:
        spec = parse_spec(text)
        assert spec.function_name == expected_name

    def test_non_decreasing_postcondition(self) -> None:
        spec = parse_spec("Output in non-decreasing order")
        assert len(spec.postconditions) > 0

    def test_unique_postcondition(self) -> None:
        spec = parse_spec("Return unique elements")
        assert any("unique" in p.lower() or "set" in p for p in spec.postconditions)


# ---------------------------------------------------------------------------
# load_spec_from_yaml tests
# ---------------------------------------------------------------------------


class TestLoadSpecFromYaml:
    """Tests for loading specs from YAML files."""

    def test_valid_yaml(self, tmp_path: Path) -> None:
        data = {
            "description": "Sort integers",
            "function_name": "sort",
            "postconditions": ["is_sorted(result)"],
        }
        yaml_file = tmp_path / "spec.yaml"
        yaml_file.write_text(yaml.dump(data))

        spec = load_spec_from_yaml(str(yaml_file))
        assert spec.description == "Sort integers"
        assert spec.function_name == "sort"

    def test_missing_description_raises(self, tmp_path: Path) -> None:
        data = {"function_name": "foo"}
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text(yaml.dump(data))

        with pytest.raises(SpecParsingError, match="description"):
            load_spec_from_yaml(str(yaml_file))

    def test_nonexistent_file_raises(self) -> None:
        with pytest.raises(SpecParsingError, match="Failed to load"):
            load_spec_from_yaml("/nonexistent/path/spec.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        yaml_file = tmp_path / "bad.yaml"
        yaml_file.write_text("description")  # not a mapping

        with pytest.raises(SpecParsingError, match="mapping"):
            load_spec_from_yaml(str(yaml_file))

    def test_full_round_trip(self, tmp_path: Path) -> None:
        data = {
            "description": "Binary search in sorted array",
            "function_name": "binary_search",
            "input_types": {"arr": "List[int]", "target": "int"},
            "output_type": "int",
            "preconditions": ["is_sorted(arr)"],
            "postconditions": ["result == -1 or arr[result] == target"],
            "edge_cases": ["arr == []"],
        }
        yaml_file = tmp_path / "spec.yaml"
        yaml_file.write_text(yaml.dump(data))

        spec = load_spec_from_yaml(str(yaml_file))
        assert spec.function_name == "binary_search"
        assert spec.preconditions == ["is_sorted(arr)"]
