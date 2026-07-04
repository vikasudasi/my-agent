from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from my_agent.messages import (
    extract_messages,
    latest_assistant_text,
    message_text,
    snippet,
    stringify_content,
)


class TestStringifyContent:
    def test_plain_string(self) -> None:
        assert stringify_content(" hello ") == "hello"

    def test_text_blocks(self) -> None:
        content = [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]
        assert stringify_content(content) == "a\nb"

    def test_none(self) -> None:
        assert stringify_content(None) == ""


class TestExtractMessages:
    def test_from_dict(self) -> None:
        messages = [HumanMessage(content="hi")]
        assert extract_messages({"messages": messages}) == messages

    def test_from_object(self) -> None:
        expected = [HumanMessage(content="hi")]

        class State:
            messages = expected

        assert extract_messages(State()) == expected


class TestLatestAssistantText:
    def test_returns_last_ai_message(self) -> None:
        messages = [
            HumanMessage(content="question"),
            AIMessage(content="answer"),
            AIMessage(content="final"),
        ]
        assert latest_assistant_text(messages) == "final"

    def test_empty_when_no_ai_messages(self) -> None:
        assert latest_assistant_text([HumanMessage(content="only user")]) == ""


class TestSnippet:
    def test_truncates_long_text(self) -> None:
        text = "word " * 30
        result = snippet(text, 20)
        assert result is not None
        assert len(result) <= 20

    def test_empty_value(self) -> None:
        assert snippet("", 20, empty="(none)") == "(none)"
        assert snippet(None, 20) is None


class TestMessageText:
    def test_delegates_to_stringify_content(self) -> None:
        message = HumanMessage(content="hello")
        assert message_text(message) == "hello"
