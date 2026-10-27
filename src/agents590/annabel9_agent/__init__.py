"""Annabel's coding agent"""

import asyncio
import json
import sys
from collections.abc import Mapping
from typing import cast

from openai.types.responses import ResponseInputItemParam, ResponseInputParam, ToolParam

from agents590.contracts import RunContext
from agents590.provider import UNCOpenAISettings


def trace(event: str, data: Mapping[str, object]) -> None:
    # event: a string decscribing the event type, e.g., "model_request", "model_response", "function_call", "function_call_output"
    # data: contains details about the events
    print(
        "AGENT_TRACE:"
        + json.dumps(
            {
                "event": event,
                "data": data,
            },
            default=str,
        ),
        file=sys.stderr,
        flush=True,
    )


class AnnabelAgent:
    """Scaffold for a model/tool loop using the shared standalone interface."""

    def provider_settings(self, context: RunContext) -> UNCOpenAISettings:
        """Prefer the per-run model to the environment's configured deployment."""
        return UNCOpenAISettings.from_env(model=context.model)

    async def run(self, instruction: str, context: RunContext) -> str:
        """Run the agent with the given instruction and context."""
        # Start with settings = self.provider_settings(context), then open
        # settings.create_async_client() and use model=settings.model.
        # Send Responses requests with store=False and background=False.
        # Run shell tools with context.cwd as their explicit working directory.

        settings = self.provider_settings(context)

        tools: list[ToolParam] = [
            {
                "type": "function",
                "name": "run_command",
                "description": (
                    "Execute a shell command to inspect files, modify code, or run tests."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Shell command to execute.",
                        }
                    },
                    "required": ["command"],
                    "additionalProperties": False,
                },
                "strict": True,
            }
        ]

        messages: ResponseInputParam = [
            {
                "role": "developer",
                "content": (
                    "You are a coding agent. "
                    "Inspect files before modifying them. "
                    "Complete the requested coding task. "
                    "Use shell commands to read and edit files. "
                    "After editing files, inspect the resulting contents and verify that "
                    "all requested requirements are met. "
                    "Check for unintended changes before reporting completion."
                    "Run tests after making changes."
                    "If the tests fail inspect the failures, fix the problems, and rerun them."
                    "Do not claim success until the tests pass."
                    "Summarize your changes when finished."
                ),
            },
            {
                "role": "user",
                "content": instruction,
            },
        ]
        max_iterations = 15

        async with settings.create_async_client() as client:
            for _ in range(max_iterations):
                trace("model_request", {"messages": messages, "tools": tools})
                response = await client.responses.create(
                    model=settings.model,
                    input=messages,
                    tools=tools,
                    store=False,
                    background=False,
                )

                trace(
                    "model_response",
                    {
                        "model": settings.model,
                        "output": [item.model_dump(exclude_none=True) for item in response.output],
                        "input_tokens": (response.usage.input_tokens if response.usage else None),
                        "output_tokens": (response.usage.output_tokens if response.usage else None),
                    },
                )

                for item in response.output:
                    # SDK serialization loses the specific Responses item type.
                    messages.append(
                        cast(ResponseInputItemParam, item.model_dump(exclude_none=True))
                    )

                tool_calls = [item for item in response.output if item.type == "function_call"]

                if not tool_calls:
                    return response.output_text or "Task completed."

                for call in tool_calls:
                    arguments = json.loads(call.arguments)
                    command = str(arguments["command"])
                    trace("function_call", {"call_id": call.call_id, "command": command})

                    process = await asyncio.create_subprocess_shell(
                        command,
                        cwd=context.cwd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    try:
                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(),
                            timeout=30,
                        )
                        result = (
                            f"Exit code: {process.returncode}\n"
                            f"STDOUT:\n"
                            f"{stdout.decode(errors='replace')[:12000]}\n"
                            f"STDERR:\n"
                            f"{stderr.decode(errors='replace')[:4000]}"
                        )
                    except TimeoutError:
                        process.kill()
                        await process.communicate()
                        result = "Command timed out after 30 seconds."

                    trace("function_call_output", {"call_id": call.call_id, "output": result})
                    messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": result,
                        }
                    )

        return "Agent reached the maximum step limit."
