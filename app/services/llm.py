from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from loguru import logger

from app.ai.config.agents import AgentConfig


async def run_agent(
    config: AgentConfig, user_prompt: str, output_schema: dict | None = None
) -> tuple[str | dict, float]:
    """Run a single-shot, tool-free Claude call for one specialist agent.

    If output_schema is given, returns the validated structured_output dict; otherwise
    returns the raw result text. Second element is always the call cost in USD.
    Raises RuntimeError if the SDK reports an error.
    """
    options = ClaudeAgentOptions(
        system_prompt=config.system_prompt,
        model=config.model,
        effort=config.effort,
        max_turns=config.max_turns,
        allowed_tools=[],
        output_format={"type": "json_schema", "schema": output_schema} if output_schema else None,
    )

    logger.debug(f"ACTION: run_agent | input=agent={config.name} prompt_len={len(user_prompt)}")

    result: str | dict = ""
    cost_usd = 0.0
    saw_result_message = False
    async for message in query(prompt=user_prompt, options=options):
        if isinstance(message, ResultMessage):
            saw_result_message = True
            if message.is_error:
                logger.error(f"FAILED: run_agent | agent={config.name} | reason={message.result}")
                raise RuntimeError(f"{config.name} agent call failed: {message.result}")
            cost_usd = message.total_cost_usd or 0.0
            if output_schema is not None and message.structured_output is not None:
                result = message.structured_output
            else:
                result = message.result or ""

    if not saw_result_message:
        logger.error(f"FAILED: run_agent | agent={config.name} | reason=no ResultMessage yielded by query()")
        raise RuntimeError(
            f"{config.name} agent call produced no ResultMessage (process likely failed silently)."
        )

    logger.success(f"ACTION: run_agent | output=agent={config.name} cost_usd={cost_usd}")
    return result, cost_usd
