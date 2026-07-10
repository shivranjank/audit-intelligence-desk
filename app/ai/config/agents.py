from dataclasses import dataclass
from pathlib import Path

import yaml

_PROMPTS_PATH = Path("app/ai/prompt/all_sample_prompt.yaml")
_PROMPTS = yaml.safe_load(_PROMPTS_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class AgentConfig:
    name: str
    system_prompt: str
    model: str
    effort: str
    max_turns: int = 1


# Model choice: "sonnet" for every role. Percy and Moody make nuanced, citation-bound
# policy judgments (including resisting adversarial injection) that Haiku is too weak
# for; Opus is unnecessary cost for this task's complexity at batch volume (50
# transactions x 2 LLM calls). Sonnet is the cost/quality balance point.
HERMIONE = AgentConfig(name="hermione", system_prompt=_PROMPTS["hermione"], model="sonnet", effort="low")
PERCY = AgentConfig(name="percy", system_prompt=_PROMPTS["percy"], model="sonnet", effort="medium")
# Moody gets the highest effort: it's the last line of defense against injection and false positives.
MOODY = AgentConfig(name="moody", system_prompt=_PROMPTS["moody"], model="sonnet", effort="high")
