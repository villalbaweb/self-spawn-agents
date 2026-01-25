"""
Unit tests for cost tracking module.
"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from agents.cost.pricing import ModelPricing, TokenPricing, Provider
from agents.cost.models import CostRecord, CostType, CostSummary
from agents.cost.tracker import CostTracker
from agents.cost.callback import CostTrackingCallback
from agents.cost.budget_guard import BudgetGuard, BudgetExceededError, check_budget


class TestModelPricing:
    """Tests for pricing configuration and calculation."""
    
    def test_get_pricing_openai_gpt4o(self):
        pricing = ModelPricing.get_pricing("gpt-4o")
        assert pricing.input == 2.50
        assert pricing.output == 10.00
        assert pricing.cached_input == 1.25
    
    def test_get_pricing_openai_mini(self):
        pricing = ModelPricing.get_pricing("gpt-4o-mini")
        assert pricing.input == 0.15
        assert pricing.output == 0.60
    
    def test_get_pricing_anthropic(self):
        pricing = ModelPricing.get_pricing("claude-3-5-sonnet-20241022")
        assert pricing.input == 3.00
        assert pricing.output == 15.00
    
    def test_get_pricing_unknown_model(self):
        pricing = ModelPricing.get_pricing("unknown-model-xyz")
        assert pricing.input == 0.0
        assert pricing.output == 0.0
    
    def test_calculate_cost_basic(self):
        # 1000 input + 500 output for gpt-4o
        # (1000 * 2.50 / 1M) + (500 * 10.00 / 1M) = 0.0025 + 0.005 = 0.0075
        cost = ModelPricing.calculate_cost(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )
        assert abs(cost - 0.0075) < 0.0001
    
    def test_calculate_cost_with_cache(self):
        # 800 regular + 200 cached input, 500 output for gpt-4o
        # (800 * 2.50 / 1M) + (200 * 1.25 / 1M) + (500 * 10.00 / 1M)
        # = 0.002 + 0.00025 + 0.005 = 0.00725
        cost = ModelPricing.calculate_cost(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            cached_input_tokens=200,
        )
        assert abs(cost - 0.00725) < 0.0001
    
    def test_resolve_provider_from_model(self):
        assert ModelPricing._resolve_provider("gpt-4o", None) == Provider.OPENAI
        assert ModelPricing._resolve_provider("claude-3-opus", None) == Provider.ANTHROPIC
        assert ModelPricing._resolve_provider("deepseek-chat", None) == Provider.DEEPSEEK
        assert ModelPricing._resolve_provider("local-llama", None) == Provider.LOCAL


class TestCostRecord:
    """Tests for CostRecord dataclass."""
    
    def test_to_dict_serialization(self):
        record = CostRecord(
            type=CostType.LLM,
            cost_usd=0.01,
            task_id="task-123",
            agent_id="agent-1",
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
        )
        data = record.to_dict()
        
        assert data["type"] == "llm"
        assert data["cost_usd"] == 0.01
        assert data["task_id"] == "task-123"
        assert data["model"] == "gpt-4o"
    
    def test_from_dict_deserialization(self):
        data = {
            "type": "tool",
            "cost_usd": 0.001,
            "timestamp": "2026-01-25T12:00:00",
            "task_id": "task-456",
            "tool_name": "web_search",
        }
        record = CostRecord.from_dict(data)
        
        assert record.type == CostType.TOOL
        assert record.cost_usd == 0.001
        assert record.tool_name == "web_search"


class TestCostTracker:
    """Tests for CostTracker service."""
    
    @pytest.fixture(autouse=True)
    def reset_tracker(self):
        """Reset singleton before each test."""
        CostTracker.reset_instance()
        yield
        CostTracker.reset_instance()
    
    def test_singleton_pattern(self):
        tracker1 = CostTracker.get_instance()
        tracker2 = CostTracker.get_instance()
        assert tracker1 is tracker2
    
    def test_record_llm(self):
        tracker = CostTracker.get_instance()
        record = tracker.record_llm(
            model="gpt-4o",
            input_tokens=1000,
            output_tokens=500,
            task_id="test-task",
            agent_id="test-agent",
        )
        
        assert record.type == CostType.LLM
        assert record.model == "gpt-4o"
        assert record.task_id == "test-task"
        assert record.cost_usd > 0
    
    def test_record_tool(self):
        tracker = CostTracker.get_instance()
        record = tracker.record_tool(
            tool_name="web_search",
            cost=0.001,
            task_id="test-task",
        )
        
        assert record.type == CostType.TOOL
        assert record.tool_name == "web_search"
        assert record.cost_usd == 0.001
    
    def test_get_total_cost(self):
        tracker = CostTracker.get_instance()
        
        tracker.record_llm("gpt-4o", 1000, 500, task_id="t1")
        tracker.record_llm("gpt-4o-mini", 2000, 1000, task_id="t1")
        tracker.record_tool("search", 0.001, task_id="t1")
        
        total = tracker.get_total_cost()
        assert total > 0
    
    def test_get_total_cost_by_task(self):
        tracker = CostTracker.get_instance()
        
        tracker.record_llm("gpt-4o", 1000, 500, task_id="task-a")
        tracker.record_llm("gpt-4o", 2000, 1000, task_id="task-b")
        
        cost_a = tracker.get_total_cost("task-a")
        cost_b = tracker.get_total_cost("task-b")
        
        assert cost_a < cost_b  # task-b has more tokens
    
    def test_get_cost_by_type(self):
        tracker = CostTracker.get_instance()
        
        tracker.record_llm("gpt-4o", 1000, 500)
        tracker.record_tool("search", 0.01)
        tracker.record_embedding("text-embedding-3-small", 500)
        
        by_type = tracker.get_cost_by_type()
        assert "llm" in by_type
        assert "tool" in by_type
        assert "embedding" in by_type
    
    def test_get_summary(self):
        tracker = CostTracker.get_instance()
        
        tracker.record_llm("gpt-4o", 1000, 500, agent_id="agent-1", node_name="node-a")
        tracker.record_llm("gpt-4o-mini", 2000, 1000, agent_id="agent-2", node_name="node-b")
        
        summary = tracker.get_summary()
        
        assert summary.call_count == 2
        assert summary.total_input_tokens == 3000
        assert summary.total_output_tokens == 1500
        assert "gpt-4o" in summary.by_model
        assert "agent-1" in summary.by_agent
    
    def test_listener_notification(self):
        tracker = CostTracker.get_instance()
        received: list = []
        
        def listener(record):
            received.append(record)
        
        tracker.add_listener(listener)
        tracker.record_llm("gpt-4o", 1000, 500)
        
        assert len(received) == 1
        assert received[0].model == "gpt-4o"
    
    def test_task_scope_context(self):
        tracker = CostTracker.get_instance()
        
        with tracker.task_scope("scoped-task") as scope:
            tracker.record_llm("gpt-4o", 1000, 500, task_id="scoped-task")
            assert scope.get_cost() > 0
    
    def test_reset_clears_records(self):
        tracker = CostTracker.get_instance()
        tracker.record_llm("gpt-4o", 1000, 500)
        
        assert len(tracker.records) == 1
        tracker.reset()
        assert len(tracker.records) == 0
    
    def test_to_usage_stats_format(self):
        tracker = CostTracker.get_instance()
        tracker.record_llm("gpt-4o", 1000, 500)
        tracker.record_tool("search", 0.01)
        
        stats = tracker.to_usage_stats()
        
        assert "cost" in stats
        assert "input_tokens" in stats
        assert "output_tokens" in stats
        assert "llm_calls" in stats
        assert "tool_calls" in stats


class TestCostTrackingCallback:
    """Tests for LangChain callback handler."""
    
    def test_callback_initialization(self):
        callback = CostTrackingCallback(
            task_id="task-1",
            agent_id="agent-1",
        )
        assert callback.task_id == "task-1"
        assert callback.agent_id == "agent-1"
    
    def test_on_llm_end_extracts_usage(self):
        callback = CostTrackingCallback(task_id="test")
        
        # Mock LLMResult
        mock_response = MagicMock()
        mock_response.llm_output = {
            "token_usage": {
                "prompt_tokens": 1000,
                "completion_tokens": 500,
                "total_tokens": 1500,
            },
            "model_name": "gpt-4o",
        }
        mock_response.generations = [[MagicMock()]]
        
        from uuid import uuid4
        callback.on_llm_end(mock_response, run_id=uuid4())
        
        assert len(callback.records) == 1
        assert callback.records[0].input_tokens == 1000
        assert callback.records[0].output_tokens == 500
        assert callback.records[0].model == "gpt-4o"
    
    def test_get_total_cost(self):
        callback = CostTrackingCallback()
        
        mock_response = MagicMock()
        mock_response.llm_output = {
            "token_usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            "model_name": "gpt-4o",
        }
        
        from uuid import uuid4
        callback.on_llm_end(mock_response, run_id=uuid4())
        
        assert callback.get_total_cost() > 0
    
    def test_get_cost_by_agent(self):
        callback = CostTrackingCallback()
        
        mock_response = MagicMock()
        mock_response.llm_output = {
            "token_usage": {"prompt_tokens": 1000, "completion_tokens": 500},
            "model_name": "gpt-4o",
        }
        
        from uuid import uuid4
        callback.on_llm_end(mock_response, run_id=uuid4(), metadata={"agent_id": "agent-x"})
        
        by_agent = callback.get_cost_by_agent()
        assert "agent-x" in by_agent
    
    def test_reset_clears_records(self):
        callback = CostTrackingCallback()
        
        mock_response = MagicMock()
        mock_response.llm_output = {
            "token_usage": {"prompt_tokens": 100, "completion_tokens": 50},
            "model_name": "gpt-4o-mini",
        }
        
        from uuid import uuid4
        callback.on_llm_end(mock_response, run_id=uuid4())
        
        assert len(callback.records) == 1
        callback.reset()
        assert len(callback.records) == 0


class TestBudgetGuard:
    """Tests for budget enforcement."""
    
    def test_check_below_all_limits(self):
        guard = BudgetGuard(warn_limit=5.0, soft_limit=8.0, hard_limit=10.0)
        
        # Should not raise
        result = guard.check(current_cost=3.0, task_id="test")
        assert "review_required" not in result or not result["review_required"]
    
    def test_check_exceeds_warn_limit(self, capsys):
        guard = BudgetGuard(warn_limit=5.0, hard_limit=10.0)
        
        guard.check(current_cost=6.0, task_id="test")
        captured = capsys.readouterr()
        assert "warning" in captured.out.lower() or "⚠️" in captured.out
    
    def test_check_exceeds_soft_limit(self):
        guard = BudgetGuard(soft_limit=5.0, hard_limit=10.0)
        
        result = guard.check(current_cost=6.0, task_id="test", state={})
        assert result.get("review_required") is True
        assert result.get("budget_exceeded") is True
    
    def test_check_exceeds_hard_limit(self):
        guard = BudgetGuard(hard_limit=10.0)
        
        with pytest.raises(BudgetExceededError) as exc_info:
            guard.check(current_cost=11.0, task_id="test")
        
        assert exc_info.value.current_cost == 11.0
        assert exc_info.value.limit == 10.0
    
    def test_from_config(self):
        config = {"max_cost": 10.0, "warn_cost": 5.0}
        guard = BudgetGuard.from_config(config)
        
        # Should have 2 thresholds
        assert len(guard.thresholds) == 2
    
    def test_warn_only_once_per_task(self, capsys):
        guard = BudgetGuard(warn_limit=5.0)
        
        guard.check(current_cost=6.0, task_id="test")
        guard.check(current_cost=7.0, task_id="test")
        
        captured = capsys.readouterr()
        # Should only have one warning
        assert captured.out.count("⚠️") == 1


class TestCheckBudgetFunction:
    """Tests for standalone check_budget function."""
    
    def test_no_budget_configured(self):
        state = {"usage_stats": {"cost": 100.0}}
        # Should not raise when no budget
        check_budget(state)
    
    def test_within_budget(self):
        state = {
            "budget_config": {"max_cost": 10.0},
            "usage_stats": {"cost": 5.0},
        }
        # Should not raise
        check_budget(state)
    
    def test_exceeds_budget(self):
        state = {
            "budget_config": {"max_cost": 10.0},
            "usage_stats": {"cost": 15.0},
        }
        
        with pytest.raises(BudgetExceededError):
            check_budget(state)
    
    def test_max_spend_override(self):
        state = {
            "budget_config": {"max_cost": 100.0},
            "usage_stats": {"cost": 15.0},
        }
        
        # Override with lower limit
        with pytest.raises(BudgetExceededError):
            check_budget(state, max_spend=10.0)
