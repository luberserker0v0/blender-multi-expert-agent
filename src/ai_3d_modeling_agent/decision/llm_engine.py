"""Endpoint-backed decision engine experiment."""

import json
from dataclasses import dataclass

from ai_3d_modeling_agent.decision.base import DecisionEngine
from ai_3d_modeling_agent.prompts import read_markdown_prompt
from ai_3d_modeling_agent.schemas.actions import Action
from ai_3d_modeling_agent.schemas.gap_report import GapReport
from ai_3d_modeling_agent.services.llm_endpoint import OpenAiCompatibleEndpointClient
from ai_3d_modeling_agent.utils.llm_parser import extract_json_from_llm


@dataclass
class EndpointDecisionConfig:
    max_tokens: int = 1024
    temperature: float = 0.3


class EndpointLlmDecisionEngine(DecisionEngine):
    def __init__(
        self,
        client: OpenAiCompatibleEndpointClient,
        config: EndpointDecisionConfig = None,
    ) -> None:
        self.client = client
        self.config = config or EndpointDecisionConfig()

    def decide(self, gap_report: GapReport) -> Action:
        system_prompt, user_prompt = self._build_prompts(gap_report)
        raw_response = self.client.create_chat_completion(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            max_tokens=self.config.max_tokens,
            temperature=self.config.temperature,
        )
        data = extract_json_from_llm(raw_response, context_label="LocalDecision")
        return Action(
            action_type=str(data["action_type"]),
            parameters=dict(data.get("parameters", {})),
            reason=str(data.get("reason", "LLM decision")),
        )

    def _build_prompts(self, gap_report: GapReport):
        payload = gap_report.to_dict()
        system_prompt = read_markdown_prompt("decision/llm_engine_system.md")
        user_prompt = f"Gap report:\n{json.dumps(payload, ensure_ascii=False)}"
        return system_prompt, user_prompt

