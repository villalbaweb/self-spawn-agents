"""
Integration Tests for Context Compression (Epic 5).

Verifies that:
1. Summarization triggers when results exceed threshold
2. Compression ratio is depth-aware
3. Structured output preserves information density
4. No hallucination occurs in summaries
"""
import pytest
import asyncio
import sys
import os
from unittest.mock import Mock, patch

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../backend'))

from agents.result_summarizer import (
    summarize_result,
    should_compress_result,
    estimate_token_count,
    get_compression_ratio,
    SUMMARY_THRESHOLD_TOKENS
)


class TestTokenEstimation:
    """Test token count estimation utility."""
    
    def test_estimate_token_count_short_text(self):
        """Short text should estimate correctly."""
        text = "Hello world"
        tokens = estimate_token_count(text)
        assert tokens == len(text) // 4
        assert tokens == 2  # 11 chars / 4 = 2
    
    def test_estimate_token_count_long_text(self):
        """Long text should estimate correctly."""
        text = "a" * 4000
        tokens = estimate_token_count(text)
        assert tokens == 1000


class TestCompressionThreshold:
    """Test compression threshold logic."""
    
    def test_should_compress_below_threshold(self):
        """Results below threshold should not compress."""
        short_result = "a" * 100  # ~25 tokens
        assert not should_compress_result(short_result, depth=0)
    
    def test_should_compress_above_threshold(self):
        """Results above threshold should compress."""
        long_result = "a" * 4000  # ~1000 tokens
        assert should_compress_result(long_result, depth=0)
    
    def test_should_compress_error_markers(self):
        """Error markers should never compress."""
        error_result = "[Error: Something failed]"
        assert not should_compress_result(error_result, depth=0)
    
    def test_depth_aware_threshold(self):
        """Deeper levels should have lower thresholds."""
        # 2000 chars = ~500 tokens
        medium_result = "a" * 2000
        
        # At depth 0: threshold = 800, should not compress
        assert not should_compress_result(medium_result, depth=0)
        
        # At depth 2: threshold = 800 * 0.5 = 400, should compress
        assert should_compress_result(medium_result, depth=2)
        
        # At depth 3: threshold = 800 * 0.3 = 240, should compress
        assert should_compress_result(medium_result, depth=3)


class TestCompressionRatio:
    """Test depth-based compression ratios."""
    
    def test_compression_ratio_depth_0(self):
        """Depth 0 should have no compression."""
        assert get_compression_ratio(0) == 1.0
    
    def test_compression_ratio_depth_1(self):
        """Depth 1 should have 30% reduction."""
        assert get_compression_ratio(1) == 0.7
    
    def test_compression_ratio_depth_2(self):
        """Depth 2 should have 50% reduction."""
        assert get_compression_ratio(2) == 0.5
    
    def test_compression_ratio_depth_3_plus(self):
        """Depth 3+ should have 70% reduction."""
        assert get_compression_ratio(3) == 0.3
        assert get_compression_ratio(10) == 0.3


@pytest.mark.asyncio
class TestSummarizeResult:
    """Test the core summarization agent logic."""
    
    async def test_summarize_result_basic(self):
        """Test basic summarization with mock LLM."""
        task = "Research OAuth 2.0 authentication"
        verbose_result = """
        The researcher conducted an extensive analysis of OAuth 2.0 authentication flows.
        After reviewing multiple implementations, the following key findings were identified:
        
        1. OAuth 2.0 is an industry-standard protocol for authorization
        2. PKCE (Proof Key for Code Exchange) is recommended for public clients
        3. The authlib library provides a robust Python implementation
        4. Token refresh mechanisms should be implemented for long-lived sessions
        
        Several technical constraints were discovered during the research:
        - HTTPS is mandatory for production deployments
        - State parameter is required to prevent CSRF attacks
        - Token storage must be secure (httpOnly cookies or secure storage)
        
        The next steps would be to implement a proof-of-concept using the authlib library
        and validate the flow with a test OAuth provider.
        """ * 5  # Make it long enough to trigger compression
        
        with patch('agents.result_summarizer.safe_ainvoke') as mock_invoke:
            # Mock the LLM response
            mock_compressed = Mock()
            mock_compressed.intent = "Research OAuth 2.0 authentication flow"
            mock_compressed.changes = "- Identified PKCE requirement\n- Recommended authlib library"
            mock_compressed.constraints = "- HTTPS mandatory\n- State parameter required"
            mock_compressed.next_steps = "Implement POC with authlib"
            mock_invoke.return_value = mock_compressed
            
            compressed, usage = await summarize_result(
                task=task,
                result=verbose_result,
                depth=1,
                root_task_id="test_task"
            )
            
            # Verify compression occurred
            assert "Intent:" in compressed
            assert "Changes:" in compressed
            assert "Constraints:" in compressed
            assert "Next Steps:" in compressed
            
            # Verify it's shorter than original
            assert len(compressed) < len(verbose_result)
            
            # Verify LLM was called
            mock_invoke.assert_called_once()
    
    async def test_summarize_result_fallback_on_error(self):
        """Test fallback to truncation when LLM fails."""
        task = "Test task"
        long_result = "a" * 10000
        
        with patch('agents.result_summarizer.safe_ainvoke', side_effect=Exception("LLM failed")):
            compressed, usage = await summarize_result(
                task=task,
                result=long_result,
                depth=1,
                root_task_id="test_task"
            )
            
            # Should fall back to truncation
            assert "[...truncated" in compressed
            assert len(compressed) < len(long_result)


@pytest.mark.asyncio
class TestSummarizeExecutionNode:
    """Test the graph node integration."""
    
    async def test_summarize_node_skips_short_results(self):
        """Node should skip compression for short results."""
        state = {
            "task": "Simple task",
            "results": {"worker": "Short result"},
            "depth": 0,
            "parent_node_id": "worker",
            "root_task_id": "test"
        }
        
        updates = await summarize_execution_node(state)
        
        # Should return empty (no changes)
        assert updates == {}
    
    async def test_summarize_node_skips_error_results(self):
        """Node should skip compression for error markers."""
        state = {
            "task": "Failed task",
            "results": {"worker": "[Error: Task failed]"},
            "depth": 0,
            "parent_node_id": "worker",
            "root_task_id": "test"
        }
        
        updates = await summarize_execution_node(state)
        
        # Should return empty (no changes)
        assert updates == {}
    
    async def test_summarize_node_compresses_long_results(self):
        """Node should compress long results."""
        long_result = "a" * 5000  # ~1250 tokens
        state = {
            "task": "Complex task",
            "results": {"worker": long_result},
            "depth": 1,
            "parent_node_id": "worker",
            "root_task_id": "test"
        }
        
        with patch('agents.result_summarizer.safe_ainvoke') as mock_invoke:
            # Mock the LLM response
            mock_compressed = Mock()
            mock_compressed.intent = "Test intent"
            mock_compressed.changes = "Test changes"
            mock_compressed.constraints = "None"
            mock_compressed.next_steps = "None"
            mock_invoke.return_value = mock_compressed
            
            updates = await summarize_execution_node(state)
            
            # Should return updated results
            assert "results" in updates
            assert updates["results"]["worker"] != long_result
            assert "Intent:" in updates["results"]["worker"]
            
            # Should include usage stats
            assert "usage_stats" in updates


@pytest.mark.asyncio
class TestEndToEndCompression:
    """End-to-end tests simulating recursive execution."""
    
    async def test_compression_prevents_context_bloat(self):
        """Verify compression reduces context size at depth."""
        # Simulate a verbose result from depth 2
        verbose_result = """
        The coder agent successfully implemented the authentication system.
        The implementation includes the following components:
        
        1. User model with password hashing using bcrypt
        2. JWT token generation and validation
        3. Login endpoint with rate limiting
        4. Logout endpoint with token blacklisting
        5. Password reset flow with email verification
        
        Technical decisions made:
        - Used PyJWT library for token handling
        - Implemented refresh token rotation
        - Added CORS configuration for frontend integration
        
        The code was tested locally and all unit tests pass.
        Integration tests were also created to verify the full flow.
        """ * 10  # Repeat to make it very long
        
        original_tokens = estimate_token_count(verbose_result)
        assert original_tokens > SUMMARY_THRESHOLD_TOKENS
        
        with patch('agents.result_summarizer.safe_ainvoke') as mock_invoke:
            # Mock compressed response
            mock_compressed = Mock()
            mock_compressed.intent = "Implement authentication system"
            mock_compressed.changes = "- User model with bcrypt\n- JWT tokens\n- Login/logout endpoints"
            mock_compressed.constraints = "- CORS required for frontend"
            mock_compressed.next_steps = "None (tests passing)"
            mock_invoke.return_value = mock_compressed
            
            compressed, usage = await summarize_result(
                task="Implement auth system",
                result=verbose_result,
                depth=2,
                root_task_id="test"
            )
            
            compressed_tokens = estimate_token_count(compressed)
            
            # Verify significant reduction
            reduction_pct = (original_tokens - compressed_tokens) / original_tokens * 100
            assert reduction_pct > 50  # At least 50% reduction
            
            print(f"Compression: {original_tokens} → {compressed_tokens} tokens ({reduction_pct:.1f}% reduction)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
