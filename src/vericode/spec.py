"""Spec parsing and representation.

Converts natural-language specifications into structured ``Spec`` objects
that drive the downstream code-generation and proof-generation pipeline.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, Field, model_validator

from vericode.exceptions import SpecParsingError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class Spec(BaseModel):
    """A structured specification for verified code generation.

    Attributes:
        description: Free-text description of the desired function.
        function_name: Identifier for the function to generate.
        input_types: Mapping of parameter names to type annotations.
        output_type: Return type annotation.
        preconditions: Logical conditions that must hold on inputs.
        postconditions: Logical conditions that must hold on outputs.
        invariants: Loop / structural invariants (optional).
        edge_cases: Interesting edge cases the implementation must handle.
    """

    description: str
    function_name: str = ""
    input_types: dict[str, str] = Field(default_factory=dict)
    output_type: str = ""
    preconditions: list[str] = Field(default_factory=list)
    postconditions: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)

    def complexity_score(self) -> float:
        """Estimate how difficult this spec is to verify.

        The score is a float in [0, 1] computed from:
        - Number of postconditions (weight 0.35)
        - Number of edge cases (weight 0.25)
        - Description length (weight 0.20)
        - Number of preconditions (weight 0.10)
        - Number of invariants (weight 0.10)

        A higher score means the spec is expected to be harder to prove.
        """
        postcond_score = min(len(self.postconditions) / 5.0, 1.0)
        edge_score = min(len(self.edge_cases) / 4.0, 1.0)
        desc_score = min(len(self.description) / 500.0, 1.0)
        precond_score = min(len(self.preconditions) / 4.0, 1.0)
        invariant_score = min(len(self.invariants) / 3.0, 1.0)

        raw = (
            0.35 * postcond_score
            + 0.25 * edge_score
            + 0.20 * desc_score
            + 0.10 * precond_score
            + 0.10 * invariant_score
        )
        return round(min(raw, 1.0), 4)

    @model_validator(mode="after")
    def _infer_function_name(self) -> Spec:
        """Best-effort extraction of a function name from the description."""
        if not self.function_name and self.description:
            self.function_name = _extract_function_name(self.description)
        return self


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_VERB_MAP: dict[str, str] = {
    "sort": "sort",
    "search": "search",
    "find": "find",
    "merge": "merge",
    "insert": "insert",
    "delete": "delete",
    "remove": "remove",
    "reverse": "reverse",
    "compute": "compute",
    "calculate": "calculate",
    "filter": "filter",
    "validate": "validate",
    "check": "check",
    "count": "count",
    "sum": "sum_values",
    "max": "find_max",
    "min": "find_min",
    "binary search": "binary_search",
    "binary_search": "binary_search",
}

_POSTCONDITION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sorted", re.IGNORECASE), "is_sorted(result)"),
    (re.compile(r"permutation", re.IGNORECASE), "is_permutation(result, input)"),
    (
        re.compile(r"non-decreasing", re.IGNORECASE),
        "all(result[i] <= result[i+1] for i in range(len(result)-1))",
    ),
    (
        re.compile(r"unique|distinct", re.IGNORECASE),
        "len(result) == len(set(result))",
    ),
]

_EDGE_CASE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"empty", re.IGNORECASE), "input == []"),
    (re.compile(r"single element", re.IGNORECASE), "len(input) == 1"),
    (re.compile(r"negative", re.IGNORECASE), "contains_negative(input)"),
    (re.compile(r"duplicate", re.IGNORECASE), "contains_duplicates(input)"),
]


def _extract_function_name(text: str) -> str:
    """Heuristically extract a snake_case function name from a description."""
    lower = text.lower()
    # Check multi-word keys first (longest match)
    for phrase in sorted(_VERB_MAP, key=len, reverse=True):
        if phrase in lower:
            return _VERB_MAP[phrase]
    # Fallback: first verb-like word
    words = re.findall(r"[a-z]+", lower)
    return words[0] if words else "generated_function"


def _extract_postconditions(text: str) -> list[str]:
    """Extract formal-ish postconditions from natural language."""
    found: list[str] = []
    for pattern, condition in _POSTCONDITION_PATTERNS:
        if pattern.search(text):
            found.append(condition)
    return found


def _extract_edge_cases(text: str) -> list[str]:
    """Extract edge cases mentioned in the description."""
    found: list[str] = []
    for pattern, case in _EDGE_CASE_PATTERNS:
        if pattern.search(text):
            found.append(case)
    return found


def parse_spec(text: str) -> Spec:
    """Parse a natural-language specification string into a ``Spec``.

    Args:
        text: A plain-English description of the desired function, including
            any constraints on inputs, outputs, and edge cases.

    Returns:
        A ``Spec`` populated with as many fields as can be inferred.

    Raises:
        SpecParsingError: If *text* is empty or un-parseable.
    """
    text = text.strip()
    if not text:
        raise SpecParsingError("Spec text must not be empty")

    logger.debug("Parsing spec from natural language", extra={"length": len(text)})

    function_name = _extract_function_name(text)
    postconditions = _extract_postconditions(text)
    edge_cases = _extract_edge_cases(text)

    return Spec(
        description=text,
        function_name=function_name,
        postconditions=postconditions,
        edge_cases=edge_cases,
    )


def load_spec_from_yaml(path: str) -> Spec:
    """Load a ``Spec`` from a YAML file.

    The YAML file should contain keys matching ``Spec`` field names.

    Args:
        path: Filesystem path to the YAML spec file.

    Returns:
        A validated ``Spec``.

    Raises:
        SpecParsingError: If the file cannot be read or parsed.
    """
    try:
        with open(path) as fh:
            data: Any = yaml.safe_load(fh)
    except (OSError, yaml.YAMLError) as exc:
        raise SpecParsingError(
            f"Failed to load spec from '{path}'", details=str(exc)
        ) from exc

    if not isinstance(data, dict):
        raise SpecParsingError(
            f"Expected a YAML mapping in '{path}', got {type(data).__name__}"
        )

    if "description" not in data:
        raise SpecParsingError("Spec YAML must contain a 'description' field")

    return Spec(**data)
