from pathlib import Path

import yaml

PROMPTS_DIR = Path("app/ai/prompt")
PROMPT_CONFIG_PATH = Path("config/prompt_config.yaml")


def _load_prompt_config() -> dict:
    return yaml.safe_load(PROMPT_CONFIG_PATH.read_text(encoding="utf-8")) or {}


def load_prompt(agent_name: str) -> str:
    """Load an agent's system prompt, falling back to v1 if its configured version
    is missing (so a missing/broken version file never breaks a run)."""
    config = _load_prompt_config()
    configured_version = config.get("agents", {}).get(agent_name, config.get("default_version", "v1"))

    tried: list[str] = []
    for version in (configured_version, "v1"):
        if version in tried:
            continue
        tried.append(version)
        path = PROMPTS_DIR / agent_name / version / "prompt.yaml"
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            return data["system"]

    raise FileNotFoundError(f"No prompt found for agent={agent_name!r}, tried versions {tried}")
