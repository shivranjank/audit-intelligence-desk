from dataclasses import dataclass
from pathlib import Path

import yaml

from app.ai.config.prompt_loader import load_prompt

MODEL_CONFIG_PATH = Path("config/model_config.yaml")
_MODEL_CONFIG = yaml.safe_load(MODEL_CONFIG_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt: str
    model: str
    effort: str
    max_turns: int = 1


def _build_config(name: str) -> AgentConfig:
    settings = _MODEL_CONFIG[name]
    return AgentConfig(
        name=name,
        system_prompt=load_prompt(name),
        model=settings["model"],
        effort=settings["effort"],
        max_turns=settings.get("max_turns", 1),
    )


HERMIONE = _build_config("hermione")
PERCY = _build_config("percy")
MOODY = _build_config("moody")
