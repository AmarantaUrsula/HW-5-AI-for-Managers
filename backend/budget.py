"""Token-spend guard: a hard cap of $500 per session, with a ratchet as spend approaches it.

Cost = tokens × the model's price from the genai-prices table that ships with
PydanticAI (gpt-6-luna: $0.20 per million input tokens, $0.75 per million
output tokens). At RATCHET_AT of the budget, the guard switches every new
model request to RATCHET_MODEL with a smaller output cap. HW5 rule 10 allows
only gpt-6-luna, so the default ratchet keeps that model and tightens the
token limits instead. At 100%, no new model request is allowed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from genai_prices import Usage, calc_price
from pydantic_ai import RunUsage

BUDGET_USD = float(os.environ.get("HW5_TOKEN_BUDGET_USD", "500"))
RATCHET_AT = float(os.environ.get("HW5_RATCHET_AT", "0.8"))
NORMAL_MAX_TOKENS = 4096
RATCHET_MAX_TOKENS = 1024


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class BudgetGuard:
    model: str
    ratchet_model: str
    budget_usd: float = BUDGET_USD
    spent_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    _price_in: float = field(init=False)
    _price_out: float = field(init=False)

    def __post_init__(self) -> None:
        price = calc_price(Usage(input_tokens=1_000_000, output_tokens=1_000_000),
                           model_ref=self.model, provider_id="openai")
        self._price_in = float(price.input_price) / 1_000_000
        self._price_out = float(price.output_price) / 1_000_000

    @property
    def ratcheted(self) -> bool:
        return self.spent_usd >= self.budget_usd * RATCHET_AT

    def add(self, delta_in: int, delta_out: int) -> None:
        self.input_tokens += delta_in
        self.output_tokens += delta_out
        self.spent_usd += delta_in * self._price_in + delta_out * self._price_out

    def check(self) -> None:
        """Call before every model request."""
        if self.spent_usd >= self.budget_usd:
            raise BudgetExceeded(
                f"Token spend ${self.spent_usd:.4f} reached the ${self.budget_usd:.2f} budget; stopping."
            )

    def current_model(self) -> str:
        return self.ratchet_model if self.ratcheted else self.model

    def max_tokens(self) -> int:
        return RATCHET_MAX_TOKENS if self.ratcheted else NORMAL_MAX_TOKENS


class UsageTracker:
    """Turns a run's cumulative RunUsage into per-step deltas for the BudgetGuard."""

    def __init__(self, guard: BudgetGuard) -> None:
        self.guard = guard
        self.last_in = 0
        self.last_out = 0

    def update(self, usage: RunUsage) -> None:
        d_in, d_out = usage.input_tokens - self.last_in, usage.output_tokens - self.last_out
        if d_in or d_out:
            self.guard.add(d_in, d_out)
        self.last_in, self.last_out = usage.input_tokens, usage.output_tokens
