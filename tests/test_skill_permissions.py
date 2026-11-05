"""Skills must not pre-approve shell commands (S5).

A skill reads untrusted repository text. If its frontmatter pre-approves
Bash, text in a scanned repo can steer the model into running commands
with no prompt. Shell commands from these skills must be approved by the
user each time.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SKILLS = sorted(p for p in ROOT.rglob("SKILL.md") if ".git" not in p.parts)


def _frontmatter(text: str) -> str:
    m = re.match(r"^---\n(.*?)\n---\n", text.replace("\r\n", "\n"), re.S)
    return m.group(1) if m else ""


def test_skills_found():
    assert len(SKILLS) >= 2


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: str(p.relative_to(ROOT)))
def test_skill_does_not_preapprove_shell(skill):
    fm = _frontmatter(skill.read_text(encoding="utf-8"))
    allowed = " ".join(re.findall(r"(?m)^allowed-tools:(.*)$", fm))
    assert "Bash" not in allowed, f"{skill} pre-approves {allowed.strip()}"
