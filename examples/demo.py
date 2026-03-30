#!/usr/bin/env python3
"""Offline demo for vericode.

Runs the full verification pipeline with a deterministic fake LLM provider
and a fake backend so the example is runnable without external services.
"""

from __future__ import annotations

import asyncio

from vericode import Spec, verify
from vericode.backends.base import VerificationBackend, VerificationResult
from vericode.models.base import GenerationResponse, LLMProvider


class DemoProvider(LLMProvider):
    @property
    def provider_name(self) -> str:
        return "demo-provider"

    async def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> GenerationResponse:
        code = (
            "def clamp(value: int, lower: int, upper: int) -> int:\n"
            "    if value < lower:\n"
            "        return lower\n"
            "    if value > upper:\n"
            "        return upper\n"
            "    return value\n"
        )
        proof = "theorem clamp_spec : True := by\n  trivial\n"
        return GenerationResponse(
            code=code,
            proof=proof,
            raw_text=prompt,
            model="demo-model",
            prompt_tokens=128,
            completion_tokens=96,
        )


class DemoBackend(VerificationBackend):
    @property
    def name(self) -> str:
        return "demo-backend"

    async def check_installed(self) -> bool:
        return True

    async def verify(self, proof_source: str) -> VerificationResult:
        return VerificationResult(
            success=True,
            compiler_output="demo backend accepted proof bundle",
            backend=self.name,
        )

    def format_proof_template(
        self,
        function_name: str,
        implementation: str,
        spec_conditions: list[str],
    ) -> str:
        return f"-- demo proof template for {function_name}"


async def main() -> None:
    spec = Spec(
        description="Clamp an integer into an inclusive lower/upper bound.",
        function_name="clamp",
        input_types={"value": "int", "lower": "int", "upper": "int"},
        output_type="int",
        preconditions=["lower <= upper"],
        postconditions=[
            "lower <= result <= upper",
            "result == value when lower <= value <= upper",
        ],
    )
    result = await verify(
        spec,
        language="python",
        backend=DemoBackend(),
        provider=DemoProvider(),
    )

    print("vericode demo")
    print(f"verified: {result.verified}")
    print(f"backend: {result.backend}")
    print(f"certificate issued: {result.certificate is not None}")
    print("\nimplementation:\n")
    print(result.code)


if __name__ == "__main__":
    asyncio.run(main())
