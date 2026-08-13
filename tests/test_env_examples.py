"""Keep the bilingual Docker Compose environment templates in sync."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ASSIGNMENT = re.compile(r"([A-Z][A-Z0-9_]*)=(.*)")
COMPOSE_VARIABLE = re.compile(r"\$\{([A-Z][A-Z0-9_]*)")


def _assignments(path: Path) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = ASSIGNMENT.fullmatch(stripped)
        assert match is not None, f"invalid assignment in {path.name}:{line_number}"
        entries.append((match.group(1), match.group(2)))

    keys = [key for key, _ in entries]
    assert len(keys) == len(set(keys)), f"duplicate variable in {path.name}"
    return entries


def test_bilingual_env_examples_have_identical_variables_defaults_and_order():
    english = _assignments(ROOT / ".env.example")
    chinese = _assignments(ROOT / ".env.zh-CN.example")

    assert english == chinese
    assert [key for key, _ in english[:2]] == ["ADMIN_PASSWORD", "JWT_SECRET"]


def test_env_example_variables_match_docker_compose_interpolation():
    example_keys = {key for key, _ in _assignments(ROOT / ".env.example")}
    compose_text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert example_keys == set(COMPOSE_VARIABLE.findall(compose_text))
