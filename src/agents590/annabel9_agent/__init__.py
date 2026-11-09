# """Annabel's coding agent"""

# import asyncio
# import json
# from typing import cast

# from openai.types.responses import ResponseInputItemParam, ResponseInputParam, ToolParam

# from agents590.atif import ATIFRecorder, JSONValue
# from agents590.contracts import RunContext
# from agents590.provider import UNCOpenAISettings


# class AnnabelAgent:
#     """Coding agent that records its execution using ATIF."""

#     def provider_settings(self, context: RunContext) -> UNCOpenAISettings:
#         """Prefer the per-run model to the environment's configured deployment."""
#         return UNCOpenAISettings.from_env(model=context.model)

#     async def run(self, instruction: str, context: RunContext) -> str:
#         """Run the agent with the given instruction and context."""

#         # settings = self.provider_settings(context)
#         # instructions_path = context.cwd / "AGENTS.md"
#         # project_instructions = instructions_path.read_text() if instructions_path.is_file() else ""

#         # Create the shared ATIF recorder.
#         recorder = ATIFRecorder.from_environment(
#             agent="annabel9_agent",
#             model=settings.model,
#         )

#         tools: list[ToolParam] = [
#             {
#                 "type": "function",
#                 "name": "run_command",
#                 "description": (
#                     "Execute a shell command to inspect files, modify code, or run tests."
#                 ),
#                 "parameters": {
#                     "type": "object",
#                     "properties": {
#                         "command": {
#                             "type": "string",
#                             "description": "Shell command to execute.",
#                         }
#                     },
#                     "required": ["command"],
#                     "additionalProperties": False,
#                 },
#                 "strict": True,
#             }
#         ]

#         messages: ResponseInputParam = [
#             {
#                 "role": "developer",
#                 "content": (
#                     "You are a coding agent. "
#                     "Inspect files before modifying them. "
#                     "Complete the requested coding task. "
#                     "Use shell commands to read and edit files. "
#                     "After editing files, inspect the resulting contents and verify that "
#                     "all requested requirements are met. "
#                     "Check for unintended changes before reporting completion. "
#                     "Run tests after making changes. "
#                     "If the tests fail, inspect the failures, fix the problems, and rerun them. "
#                     "Do not claim success until the tests pass. "
#                     "Read any applicable nested AGENTS.md before editing files. "
#                     "Never read or print credential files such as .env. "
#                     "Summarize your changes when finished.\n\n"
#                     f"Working directory: {context.cwd}\n"
#                     f"Repository instructions (AGENTS.md):\n{project_instructions}"
#                 ),
#             },
#             {
#                 "role": "user",
#                 "content": instruction,
#             },
#         ]

#         max_iterations = 50

#         # Keep track of total token usage.
#         total_input_tokens = 0
#         total_output_tokens = 0
#         total_cached_tokens = 0

#         def save_final_metrics() -> None:
#             """Save cumulative token usage to the ATIF trajectory."""
#             recorder.document["final_metrics"] = {
#                 "total_prompt_tokens": total_input_tokens,
#                 "total_completion_tokens": total_output_tokens,
#                 "total_cached_tokens": total_cached_tokens,
#                 "total_steps": len(recorder.document["steps"]),
#             }
#             recorder.write()

#         async with settings.create_async_client() as client:
#             for _ in range(max_iterations):
#                 response = await client.responses.create(
#                     model=settings.model,
#                     input=messages,
#                     tools=tools,
#                     store=False,
#                     background=False,
#                 )

#                 # Record token usage for this model response.
#                 usage = response.usage
#                 metrics: dict[str, JSONValue] | None = None

#                 if usage is not None:
#                     cached_tokens = (
#                         usage.input_tokens_details.cached_tokens
#                         if usage.input_tokens_details
#                         else 0
#                     )

#                     metrics = {
#                         "prompt_tokens": usage.input_tokens,
#                         "completion_tokens": usage.output_tokens,
#                         "cached_tokens": cached_tokens,
#                     }

#                     total_input_tokens += usage.input_tokens
#                     total_output_tokens += usage.output_tokens
#                     total_cached_tokens += cached_tokens

#                 # Find the shell commands requested by the model.
#                 tool_calls = [item for item in response.output if item.type == "function_call"]

#                 # Record the model response and its tool calls.
#                 atif_tool_calls: list[JSONValue] = []

#                 for call in tool_calls:
#                     try:
#                         recorded_arguments: JSONValue = json.loads(call.arguments)
#                     except json.JSONDecodeError:
#                         recorded_arguments = {"raw_arguments": call.arguments}

#                     atif_tool_calls.append(
#                         {
#                             "tool_call_id": call.call_id,
#                             "function_name": call.name,
#                             "arguments": recorded_arguments,
#                         }
#                     )

#                 # Collect text from the model's response.
#                 text_parts = [
#                     part.text
#                     for item in response.output
#                     if item.type == "message"
#                     for part in item.content
#                     if part.type == "output_text"
#                 ]

#                 fields: dict[str, JSONValue] = {"model_name": settings.model}

#                 if metrics is not None:
#                     fields["metrics"] = metrics

#                 if atif_tool_calls:
#                     fields["tool_calls"] = atif_tool_calls

#                 recorder.add(
#                     "agent",
#                     "\n".join(text_parts),
#                     **fields,
#                 )

#                 save_final_metrics()

#                 # Add model output to the conversation.
#                 for item in response.output:
#                     messages.append(
#                         cast(
#                             ResponseInputItemParam,
#                             item.model_dump(exclude_none=True),
#                         )
#                     )

#                 if not tool_calls:
#                     return response.output_text or "Task completed."

#                 # Execute each shell command requested by the model.
#                 for call in tool_calls:
#                     arguments = json.loads(call.arguments)
#                     command = str(arguments["command"])

#                     process = await asyncio.create_subprocess_shell(
#                         command,
#                         cwd=context.cwd,
#                         stdout=asyncio.subprocess.PIPE,
#                         stderr=asyncio.subprocess.PIPE,
#                     )

#                     try:
#                         stdout, stderr = await asyncio.wait_for(
#                             process.communicate(),
#                             timeout=120,
#                         )

#                         result = (
#                             f"Exit code: {process.returncode}\n"
#                             f"STDOUT:\n"
#                             f"{stdout.decode(errors='replace')[:12000]}\n"
#                             f"STDERR:\n"
#                             f"{stderr.decode(errors='replace')[:4000]}"
#                         )

#                     except TimeoutError:
#                         process.kill()
#                         await process.communicate()
#                         result = "Command timed out after 120 seconds."

#                     # Record the shell command's output.
#                     recorder.add(
#                         "environment",
#                         result,
#                         observation={
#                             "results": [
#                                 {
#                                     "source_call_id": call.call_id,
#                                     "content": result,
#                                 }
#                             ]
#                         },
#                     )

#                     save_final_metrics()

#                     # Return the tool result to the model.
#                     messages.append(
#                         {
#                             "type": "function_call_output",
#                             "call_id": call.call_id,
#                             "output": result,
#                         }
#                     )

#         save_final_metrics()
#         return "Agent reached the maximum step limit."


"""Annabel's coding agent with Agent Skills support."""

import asyncio
import json
from typing import cast

from openai.types.responses import (
    ResponseInputItemParam,
    ResponseInputParam,
    ToolParam,
)

from agents590.atif import ATIFRecorder, JSONValue
from agents590.contracts import RunContext
from agents590.provider import UNCOpenAISettings


class AnnabelAgent:
    """Coding agent that records its execution using ATIF."""

    def provider_settings(self, context: RunContext) -> UNCOpenAISettings:
        """Prefer the per-run model to the environment's configured deployment."""
        return UNCOpenAISettings.from_env(model=context.model)

    async def run(self, instruction: str, context: RunContext) -> str:
        """Run the agent with the given instruction and context."""

        settings = self.provider_settings(context)

        # Read repository instructions.
        instructions_path = context.cwd / "AGENTS.md"
        project_instructions = instructions_path.read_text() if instructions_path.is_file() else ""

        # Discover available Agent Skills.
        skills_dir = context.cwd / ".agents" / "skills"
        available_skills = []

        if skills_dir.is_dir():
            for skill_file in sorted(skills_dir.glob("*/SKILL.md")):
                content = skill_file.read_text(encoding="utf-8")

                # Read the YAML frontmatter.
                if not content.startswith("---\n"):
                    continue

                parts = content.split("---", 2)
                if len(parts) < 3:
                    continue

                metadata = {}

                for line in parts[1].strip().splitlines():
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"').strip("'")

                name = metadata.get("name")
                description = metadata.get("description")

                if name and description:
                    available_skills.append(f"- {name}: {description}\n  Path: {skill_file}")

        skills_summary = "\n".join(available_skills) if available_skills else "No skills available."

        # Create the shared ATIF recorder.
        recorder = ATIFRecorder.from_environment(
            agent="annabel9_agent",
            model=settings.model,
        )

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
                    "Check for unintended changes before reporting completion. "
                    "Run tests after making changes. "
                    "If the tests fail, inspect the failures, fix the problems, and rerun them. "
                    "Do not claim success until the tests pass. "
                    "Read any applicable nested AGENTS.md before editing files. "
                    "Never read or print credential files such as .env. "
                    "Summarize your changes when finished.\n\n"
                    f"Working directory: {context.cwd}\n"
                    f"Repository instructions (AGENTS.md):\n{project_instructions}\n\n"
                    f"Available Agent Skills:\n{skills_summary}\n\n"
                    "When a skill is relevant to the task, read its SKILL.md "
                    "using run_command before implementing the task. "
                    "Follow the relevant skill instructions."
                ),
            },
            {
                "role": "user",
                "content": instruction,
            },
        ]

        max_iterations = 50

        # Keep track of total token usage.
        total_input_tokens = 0
        total_output_tokens = 0
        total_cached_tokens = 0

        def save_final_metrics() -> None:
            """Save cumulative token usage to the ATIF trajectory."""
            recorder.document["final_metrics"] = {
                "total_prompt_tokens": total_input_tokens,
                "total_completion_tokens": total_output_tokens,
                "total_cached_tokens": total_cached_tokens,
                "total_steps": len(recorder.document["steps"]),
            }
            recorder.write()

        async with settings.create_async_client() as client:
            for _ in range(max_iterations):
                response = await client.responses.create(
                    model=settings.model,
                    input=messages,
                    tools=tools,
                    store=False,
                    background=False,
                )

                # Record token usage for this model response.
                usage = response.usage
                metrics: dict[str, JSONValue] | None = None

                if usage is not None:
                    cached_tokens = (
                        usage.input_tokens_details.cached_tokens
                        if usage.input_tokens_details
                        else 0
                    )

                    metrics = {
                        "prompt_tokens": usage.input_tokens,
                        "completion_tokens": usage.output_tokens,
                        "cached_tokens": cached_tokens,
                    }

                    total_input_tokens += usage.input_tokens
                    total_output_tokens += usage.output_tokens
                    total_cached_tokens += cached_tokens

                # Find the shell commands requested by the model.
                tool_calls = [item for item in response.output if item.type == "function_call"]

                # Record the model response and its tool calls.
                atif_tool_calls: list[JSONValue] = []

                for call in tool_calls:
                    try:
                        recorded_arguments: JSONValue = json.loads(call.arguments)
                    except json.JSONDecodeError:
                        recorded_arguments = {"raw_arguments": call.arguments}

                    atif_tool_calls.append(
                        {
                            "tool_call_id": call.call_id,
                            "function_name": call.name,
                            "arguments": recorded_arguments,
                        }
                    )

                # Collect text from the model's response.
                text_parts = [
                    part.text
                    for item in response.output
                    if item.type == "message"
                    for part in item.content
                    if part.type == "output_text"
                ]

                fields: dict[str, JSONValue] = {"model_name": settings.model}

                if metrics is not None:
                    fields["metrics"] = metrics

                if atif_tool_calls:
                    fields["tool_calls"] = atif_tool_calls

                recorder.add(
                    "agent",
                    "\n".join(text_parts),
                    **fields,
                )

                save_final_metrics()

                # Add model output to the conversation.
                for item in response.output:
                    messages.append(
                        cast(
                            ResponseInputItemParam,
                            item.model_dump(exclude_none=True),
                        )
                    )

                if not tool_calls:
                    return response.output_text or "Task completed."

                # Execute each shell command requested by the model.
                for call in tool_calls:
                    arguments = json.loads(call.arguments)
                    command = str(arguments["command"])

                    process = await asyncio.create_subprocess_shell(
                        command,
                        cwd=context.cwd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )

                    try:
                        stdout, stderr = await asyncio.wait_for(
                            process.communicate(),
                            timeout=120,
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
                        result = "Command timed out after 120 seconds."

                    # Record the shell command's output.
                    recorder.add(
                        "environment",
                        result,
                        observation={
                            "results": [
                                {
                                    "source_call_id": call.call_id,
                                    "content": result,
                                }
                            ]
                        },
                    )

                    save_final_metrics()

                    # Return the tool result to the model.
                    messages.append(
                        {
                            "type": "function_call_output",
                            "call_id": call.call_id,
                            "output": result,
                        }
                    )

        save_final_metrics()
        return "Agent reached the maximum step limit."
