"""
Model pricing configuration.

Prices are per 1M tokens (industry standard as of Jan 2026).
Update these values as providers change pricing.
"""
from typing import Dict, Optional
from dataclasses import dataclass
from enum import Enum


class Provider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPSEEK = "deepseek"
    LOCAL = "local"


@dataclass(frozen=True)
class TokenPricing:
    """Pricing per 1M tokens in USD."""
    input: float
    output: float
    cached_input: Optional[float] = None


# Pricing table: provider -> model -> TokenPricing
# Prices as of January 2026
PRICING_TABLE: Dict[Provider, Dict[str, TokenPricing]] = {
    Provider.OPENAI: {
        "gpt-4o": TokenPricing(input=2.50, output=10.00, cached_input=1.25),
        "gpt-4o-2024-11-20": TokenPricing(input=2.50, output=10.00, cached_input=1.25),
        "gpt-4o-mini": TokenPricing(input=0.15, output=0.60, cached_input=0.075),
        "gpt-4o-mini-2024-07-18": TokenPricing(input=0.15, output=0.60, cached_input=0.075),
        "gpt-4-turbo": TokenPricing(input=10.00, output=30.00),
        "gpt-4": TokenPricing(input=30.00, output=60.00),
        "gpt-3.5-turbo": TokenPricing(input=0.50, output=1.50),
        "o1": TokenPricing(input=15.00, output=60.00, cached_input=7.50),
        "o1-mini": TokenPricing(input=3.00, output=12.00, cached_input=1.50),
        "o3-mini": TokenPricing(input=1.10, output=4.40, cached_input=0.55),
    },
    Provider.ANTHROPIC: {
        "claude-3-5-sonnet-20241022": TokenPricing(input=3.00, output=15.00, cached_input=0.30),
        "claude-3-5-haiku-20241022": TokenPricing(input=0.80, output=4.00, cached_input=0.08),
        "claude-3-opus-20240229": TokenPricing(input=15.00, output=75.00, cached_input=1.50),
        "claude-3-sonnet-20240229": TokenPricing(input=3.00, output=15.00),
        "claude-3-haiku-20240307": TokenPricing(input=0.25, output=1.25, cached_input=0.03),
    },
    Provider.DEEPSEEK: {
        "deepseek-chat": TokenPricing(input=0.14, output=0.28, cached_input=0.014),
        "deepseek-reasoner": TokenPricing(input=0.55, output=2.19, cached_input=0.14),
    },
    Provider.LOCAL: {
        # Local models have zero API cost (compute cost tracked separately if needed)
        "default": TokenPricing(input=0.0, output=0.0),
    },
}


class ModelPricing:
    """
    Resolves model pricing from provider and model name.
    Thread-safe, stateless utility class.
    """

    @staticmethod
    def get_pricing(model: str, provider: Optional[str] = None) -> TokenPricing:
        """
        Get pricing for a model. Auto-detects provider if not specified.
        
        Args:
            model: Model identifier (e.g., "gpt-4o", "claude-3-5-sonnet-20241022")
            provider: Optional provider hint
            
        Returns:
            TokenPricing dataclass with input/output costs per 1M tokens
        """
        resolved_provider = ModelPricing._resolve_provider(model, provider)
        provider_pricing = PRICING_TABLE.get(resolved_provider, {})
        
        # Exact match
        if model in provider_pricing:
            return provider_pricing[model]
        
        # Fuzzy match (model family)
        for known_model, pricing in provider_pricing.items():
            if model.startswith(known_model.rsplit("-", 1)[0]):
                return pricing
        
        # Fallback: zero cost (unknown model)
        return TokenPricing(input=0.0, output=0.0)

    @staticmethod
    def _resolve_provider(model: str, provider_hint: Optional[str] = None) -> Provider:
        """Auto-detect provider from model name."""
        if provider_hint:
            try:
                return Provider(provider_hint.lower())
            except ValueError:
                pass
        
        model_lower = model.lower()
        if model_lower.startswith(("gpt-", "o1", "o3")):
            return Provider.OPENAI
        if model_lower.startswith("claude"):
            return Provider.ANTHROPIC
        if model_lower.startswith("deepseek"):
            return Provider.DEEPSEEK
        
        return Provider.LOCAL

    @staticmethod
    def calculate_cost(
        model: str,
        input_tokens: int,
        output_tokens: int,
        cached_input_tokens: int = 0,
        provider: Optional[str] = None,
    ) -> float:
        """
        Calculate cost in USD for a single LLM call.
        
        Args:
            model: Model identifier
            input_tokens: Number of prompt tokens
            output_tokens: Number of completion tokens  
            cached_input_tokens: Number of cached prompt tokens (if applicable)
            provider: Optional provider hint
            
        Returns:
            Cost in USD (float)
        """
        pricing = ModelPricing.get_pricing(model, provider)
        
        # Non-cached input tokens
        regular_input = input_tokens - cached_input_tokens
        
        cost = (
            (regular_input * pricing.input / 1_000_000)
            + (output_tokens * pricing.output / 1_000_000)
        )
        
        if cached_input_tokens > 0 and pricing.cached_input is not None:
            cost += cached_input_tokens * pricing.cached_input / 1_000_000
        
        return cost
