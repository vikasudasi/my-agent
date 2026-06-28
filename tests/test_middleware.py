from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.graph.message import RemoveMessage

from my_agent.config import SummarizationConfig
from my_agent.middleware.summarization import SummarizationMiddleware


class TestSummarizationConfigParsing:
    """SummarizationConfig is parsed correctly from raw dict values."""

    def test_defaults_are_sane(self) -> None:
        c = SummarizationConfig()
        assert c.enabled is True
        assert c.max_messages == 30
        assert c.keep_last == 10

    def test_custom_values(self) -> None:
        c = SummarizationConfig(
            enabled=True, max_messages=50, keep_last=5, model="gpt-4o-mini"
        )
        assert c.max_messages == 50
        assert c.keep_last == 5
        assert c.model == "gpt-4o-mini"


class TestSummarizationMiddlewareDisabled:
    """When summarization is disabled, after_agent is a no-op."""

    def test_returns_none_when_disabled(self) -> None:
        config = SummarizationConfig(enabled=False, model="")
        mw = SummarizationMiddleware(config, "test-model", api_key=None)
        state = {"messages": [HumanMessage(content="hi", id="1")]}
        result = mw.after_agent(state, None)
        assert result is None

    def test_returns_none_when_no_llm(self) -> None:
        config = SummarizationConfig(enabled=True, model="")
        mw = SummarizationMiddleware(config, "", api_key=None)
        assert mw._llm is None
        state = {"messages": [HumanMessage(content="hi", id="1")]}
        result = mw.after_agent(state, None)
        assert result is None

    def test_returns_none_below_threshold(self) -> None:
        config = SummarizationConfig(enabled=True, max_messages=5, keep_last=2)
        with patch(
            "my_agent.middleware.summarization.ChatOpenRouter"
        ) as mock_llm_cls:
            mock_llm_cls.return_value = MagicMock()
            mw = SummarizationMiddleware(config, "test-model", api_key="test-key")

            messages = [
                HumanMessage(content=f"msg {i}", id=str(i))
                for i in range(4)
            ]
            state = {"messages": messages}
            result = mw.after_agent(state, None)
            assert result is None


class TestSummarizationMiddlewareTriggers:
    """When the message count exceeds threshold, summary is produced."""

    def test_removes_old_messages_adds_summary(self) -> None:
        config = SummarizationConfig(enabled=True, max_messages=3, keep_last=2)

        # 5 non-system messages: msg 0,1,2,3,4
        # threshold=3, keep_last=2 → to_summarize = [:3] = msg 0,1,2
        messages = [
            HumanMessage(content=f"msg {i}", id=str(i))
            for i in range(5)
        ]

        fake_summary = "Summarized conversation."

        with patch(
            "my_agent.middleware.summarization.ChatOpenRouter"
        ) as mock_llm_cls:
            mock_llm_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.content = fake_summary
            mock_llm_instance.invoke.return_value = mock_response
            mock_llm_cls.return_value = mock_llm_instance

            mw = SummarizationMiddleware(config, "test-model", api_key="test-key")
            state = {"messages": messages}
            result = mw.after_agent(state, None)

        assert result is not None
        updates = result["messages"]

        # Should have 3 RemoveMessages + 1 summary SystemMessage
        remove_msgs = [m for m in updates if isinstance(m, RemoveMessage)]
        summary_msgs = [m for m in updates if isinstance(m, SystemMessage)]

        assert len(remove_msgs) == 3
        assert len(summary_msgs) == 1

        # Verify the right IDs are being removed (0, 1, 2 — the oldest)
        removed_ids = {rm.id for rm in remove_msgs}
        assert removed_ids == {"0", "1", "2"}

        # Verify summary message content
        assert fake_summary in summary_msgs[0].content
        assert "Summary" in summary_msgs[0].content

    def test_skips_system_messages_in_count(self) -> None:
        """SystemMessage messages (summaries, prompts) don't count toward threshold."""
        config = SummarizationConfig(enabled=True, max_messages=2, keep_last=1)

        # 2 system + 3 human = 5 total, but only 3 non-system → exceeds threshold of 2
        messages: list = [
            SystemMessage(content="system prompt", id="sys1"),
            HumanMessage(content="msg 1", id="1"),
            SystemMessage(content="previous summary", id="sys2"),
            HumanMessage(content="msg 2", id="2"),
            HumanMessage(content="msg 3", id="3"),
        ]

        with patch(
            "my_agent.middleware.summarization.ChatOpenRouter"
        ) as mock_llm_cls:
            mock_llm_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "Summary."
            mock_llm_instance.invoke.return_value = mock_response
            mock_llm_cls.return_value = mock_llm_instance

            mw = SummarizationMiddleware(config, "test-model", api_key="test-key")
            state = {"messages": messages}
            result = mw.after_agent(state, None)

        assert result is not None
        updates = result["messages"]
        remove_msgs = [m for m in updates if isinstance(m, RemoveMessage)]

        # Should remove 2 oldest non-system: msg 1 (id=1) and msg 2 (id=2)
        # msg 3 (id=3) is the last 1 kept
        removed_ids = {rm.id for rm in remove_msgs}
        assert removed_ids == {"1", "2"}

    def test_handles_llm_failure_gracefully(self) -> None:
        """When the LLM call fails, summary is still produced with a fallback."""
        config = SummarizationConfig(enabled=True, max_messages=1, keep_last=1)

        messages = [
            HumanMessage(content="msg 1", id="1"),
            HumanMessage(content="msg 2", id="2"),
        ]

        with patch(
            "my_agent.middleware.summarization.ChatOpenRouter"
        ) as mock_llm_cls:
            mock_llm_instance = MagicMock()
            mock_llm_instance.invoke.side_effect = Exception("API error")
            mock_llm_cls.return_value = mock_llm_instance

            mw = SummarizationMiddleware(config, "test-model", api_key="test-key")
            state = {"messages": messages}
            result = mw.after_agent(state, None)

        assert result is not None
        updates = result["messages"]
        remove_msgs = [m for m in updates if isinstance(m, RemoveMessage)]
        summary_msgs = [m for m in updates if isinstance(m, SystemMessage)]

        assert len(remove_msgs) == 1  # Removes msg 1
        assert len(summary_msgs) == 1
        assert "unavailable" in summary_msgs[0].content

    def test_handles_messages_without_ids(self) -> None:
        """Messages without an 'id' attribute are skipped for removal."""
        config = SummarizationConfig(enabled=True, max_messages=2, keep_last=2)

        # First 3 messages have no id → should NOT trigger removal
        messages = [
            HumanMessage(content="msg 0"),
            HumanMessage(content="msg 1"),
            HumanMessage(content="msg 2"),
        ]

        with patch(
            "my_agent.middleware.summarization.ChatOpenRouter"
        ) as mock_llm_cls:
            mock_llm_instance = MagicMock()
            mock_response = MagicMock()
            mock_response.content = "Summary."
            mock_llm_instance.invoke.return_value = mock_response
            mock_llm_cls.return_value = mock_llm_instance

            mw = SummarizationMiddleware(config, "test-model", api_key="test-key")
            state = {"messages": messages}
            result = mw.after_agent(state, None)

        assert result is None


class TestSummarizationFormatRole:
    """_format_role returns correct label for message types."""

    def test_user(self) -> None:
        assert SummarizationMiddleware._format_role(HumanMessage(content="x")) == "User"

    def test_assistant(self) -> None:
        assert SummarizationMiddleware._format_role(AIMessage(content="x")) == "Assistant"

    def test_system(self) -> None:
        assert SummarizationMiddleware._format_role(SystemMessage(content="x")) == "System"

    def test_unknown(self) -> None:
        msg = MagicMock(spec=["type"])
        msg.type = "tool"
        result = SummarizationMiddleware._format_role(msg)  # type: ignore[arg-type]
        assert result == "Tool"