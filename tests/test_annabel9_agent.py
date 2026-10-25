"""Tests for Annabel's coding agent."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents590.annabel9_agent import AnnabelAgent
from agents590.contracts import RunContext


def test_provider_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that the agent uses the requested model."""
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "default-model")

    agent = AnnabelAgent()
    context = RunContext(Path.cwd(), "test-model")

    settings = agent.provider_settings(context)

    assert settings.model == "test-model"


def test_agent_returns_response() -> None:
    """Test that the agent returns the model's final answer."""
    agent = AnnabelAgent()
    context = RunContext(Path.cwd())

    response = MagicMock()
    response.output = []
    response.output_text = "Task completed successfully."

    client = MagicMock()
    client.responses.create = AsyncMock(return_value=response)

    with patch.object(agent, "provider_settings") as mock_settings:
        mock_settings.return_value.model = "test-model"
        mock_settings.return_value.create_async_client.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        mock_settings.return_value.create_async_client.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        result = asyncio.run(agent.run("Say hello", context))

    assert result == "Task completed successfully."
    client.responses.create.assert_awaited_once()


def test_shell_command(tmp_path: Path) -> None:
    """Test that the agent executes a shell command."""
    agent = AnnabelAgent()
    context = RunContext(tmp_path)

    call = MagicMock()
    call.type = "function_call"
    call.name = "run_command"
    call.arguments = json.dumps({"command": "pwd"})
    call.call_id = "call_1"
    call.model_dump.return_value = {
        "type": "function_call",
        "name": "run_command",
        "arguments": call.arguments,
        "call_id": "call_1",
    }

    first_response = MagicMock()
    first_response.output = [call]

    second_response = MagicMock()
    second_response.output = []
    second_response.output_text = "Done"

    client = MagicMock()
    client.responses.create = AsyncMock(side_effect=[first_response, second_response])

    with patch.object(agent, "provider_settings") as mock_settings:
        mock_settings.return_value.model = "test-model"
        mock_settings.return_value.create_async_client.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        mock_settings.return_value.create_async_client.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        result = asyncio.run(agent.run("Show current directory", context))

    assert result == "Done"

    # Verify the tool result was sent back to the model.
    second_request = client.responses.create.await_args_list[1]
    messages = second_request.kwargs["input"]

    assert str(tmp_path.resolve()) in messages[-1]["output"]


def test_shell_timeout(tmp_path: Path) -> None:
    """Test that the agent handles a command timeout."""
    agent = AnnabelAgent()
    context = RunContext(tmp_path)

    call = MagicMock()
    call.type = "function_call"
    call.name = "run_command"
    call.arguments = json.dumps({"command": "sleep 10"})
    call.call_id = "call_1"
    call.model_dump.return_value = {
        "type": "function_call",
        "name": "run_command",
        "arguments": call.arguments,
        "call_id": "call_1",
    }

    first_response = MagicMock()
    first_response.output = [call]

    second_response = MagicMock()
    second_response.output = []
    second_response.output_text = "Done"

    client = MagicMock()
    client.responses.create = AsyncMock(side_effect=[first_response, second_response])

    process = MagicMock()
    process.communicate = AsyncMock(side_effect=[TimeoutError(), (b"", b"")])

    with (
        patch.object(agent, "provider_settings") as mock_settings,
        patch(
            "asyncio.create_subprocess_shell",
            new_callable=AsyncMock,
            return_value=process,
        ),
    ):
        mock_settings.return_value.model = "test-model"
        mock_settings.return_value.create_async_client.return_value.__aenter__ = AsyncMock(
            return_value=client
        )
        mock_settings.return_value.create_async_client.return_value.__aexit__ = AsyncMock(
            return_value=None
        )

        result = asyncio.run(agent.run("Run a slow command", context))

    assert result == "Done"
    process.kill.assert_called_once()
    assert process.communicate.await_count == 2
    second_request = client.responses.create.await_args_list[1]
    messages = second_request.kwargs["input"]
    assert messages[-1]["output"] == "Command timed out after 30 seconds."
