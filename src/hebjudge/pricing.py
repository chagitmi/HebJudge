"""API prices in USD per 1M tokens: (input, output).

Verified against published prices on 2026-10-21. Re-check before the full run.
"""

PRICES: dict[str, tuple[float, float]] = {
    "gpt-6-luna": (0.10, 0.50),
    "gpt-6-sol": (2.00, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1-mini": (0.40, 1.60),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    if model not in PRICES:
        raise KeyError(f"no price defined for model '{model}'")
    input_price, output_price = PRICES[model]
    return (input_tokens * input_price + output_tokens * output_price) / 1_000_000
