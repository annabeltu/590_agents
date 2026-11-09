"""Tests for Annabel's Agent Skills discovery and prompt integration."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents590.annabel9_agent import AnnabelAgent
from agents590.contracts import RunContext


@pytest.fixture
def model_request() -> tuple[AnnabelAgent, MagicMock]:
    """Return an agent and a mocked client that produces one final response."""
    response = MagicMock(usage=None)
    response.output = []
    response.output_text = "Done"

    client = MagicMock()
    client.responses.create = AsyncMock(return_value=response)

    agent = AnnabelAgent()
    settings = MagicMock(model="test-model")
    settings.create_async_client.return_value.__aenter__ = AsyncMock(return_value=client)
    settings.create_async_client.return_value.__aexit__ = AsyncMock(return_value=None)
    agent.provider_settings = MagicMock(return_value=settings)  # type: ignore[method-assign]
    return agent, client


def developer_instructions(
    model_request: tuple[AnnabelAgent, MagicMock],
    cwd: Path,
) -> str:
    """Run the mocked agent and return the developer message sent to the model."""
    agent, client = model_request
    asyncio.run(agent.run("Do the task", RunContext(cwd)))
    request = client.responses.create.await_args
    assert request is not None
    return request.kwargs["input"][0]["content"]


def write_skill(skills_dir: Path, content: str, name: str = "example") -> Path:
    """Create a skill file and return its path."""
    skill_file = skills_dir / name / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text(content, encoding="utf-8")
    return skill_file


def test_valid_skill_is_discovered_and_frontmatter_is_extracted(
    tmp_path: Path,
    model_request: tuple[AnnabelAgent, MagicMock],
) -> None:
    """A valid skill contributes its frontmatter name and description."""
    skills_dir = tmp_path / ".agents" / "skills"
    skill_file = write_skill(
        skills_dir,
        "---\nname: release-helper\ndescription: Helps prepare releases\n---\n\n# Details\n",
    )

    prompt = developer_instructions(model_request, tmp_path)

    assert "release-helper" in prompt
    assert "Helps prepare releases" in prompt
    assert str(skill_file) in prompt


def test_skill_metadata_and_path_are_in_developer_instructions(
    tmp_path: Path,
    model_request: tuple[AnnabelAgent, MagicMock],
) -> None:
    """The complete skill summary is sent in the developer message."""
    skill_file = write_skill(
        tmp_path / ".agents" / "skills",
        "---\nname: precise-name\ndescription: A precise description\n---\n",
        name="precise-skill",
    )

    prompt = developer_instructions(model_request, tmp_path)

    assert "Available Agent Skills:" in prompt
    assert f"- precise-name: A precise description\n  Path: {skill_file}" in prompt


@pytest.mark.parametrize("create_skills_dir", [False, True])
def test_missing_or_empty_skills_directory_is_handled(
    tmp_path: Path,
    model_request: tuple[AnnabelAgent, MagicMock],
    create_skills_dir: bool,
) -> None:
    """No skills directory, and an empty one, both produce a usable prompt."""
    if create_skills_dir:
        (tmp_path / ".agents" / "skills").mkdir(parents=True)

    prompt = developer_instructions(model_request, tmp_path)

    assert "Available Agent Skills:\nNo skills available." in prompt


@pytest.mark.parametrize(
    "frontmatter",
    [
        "name: missing-delimiters\ndescription: no opening or closing delimiter\n",
        "---\nname: no-closing-delimiter\ndescription: incomplete\n",
        "---\nthis is not frontmatter\n---\n",
        "---\nname: missing-description\n---\n",
        "---\ndescription: missing-name\n---\n",
    ],
)
def test_invalid_or_incomplete_skill_frontmatter_is_ignored(
    tmp_path: Path,
    model_request: tuple[AnnabelAgent, MagicMock],
    frontmatter: str,
) -> None:
    """Malformed frontmatter and incomplete metadata do not advertise a skill."""
    write_skill(tmp_path / ".agents" / "skills", frontmatter)

    prompt = developer_instructions(model_request, tmp_path)

    assert "No skills available." in prompt
    assert "missing-delimiters" not in prompt
    assert "no-closing-delimiter" not in prompt
    assert "missing-description" not in prompt
    assert "missing-name" not in prompt
