"""OpenAI-compatible endpoint client for llama-server style backends."""

import base64
import json
import mimetypes
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Type
from urllib import request
from urllib.error import HTTPError, URLError

from ai_3d_modeling_agent.multi_expert.core.expert import SamplingOptions


@dataclass
class OpenAiCompatibleEndpointConfig:
    base_url: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    timeout_seconds: float = 60.0
    multimodal_timeout_seconds: float = 180.0
    reconnect_attempts: int = 10
    reconnect_backoff_seconds: float = 2.0

    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/chat/completions"

    def get_models_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/v1/models"



class OpenAiCompatibleEndpointClient:
    def __init__(self, config: OpenAiCompatibleEndpointConfig) -> None:
        self.config = config

    def create_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = request.Request(
            self.config.chat_completions_url(),
            data=body,
            headers=headers,
            method="POST",
        )

        response_data = self._request_json_with_retry(req, timeout_seconds=self.config.timeout_seconds)

        return self._extract_text(response_data)

    def call(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        response_model: Optional[Type] = None,
        sampling: Optional[SamplingOptions] = None,
    ) -> str:
        """Call the LLM and return the text response.

        Satisfies the multi-expert ``LlmInterface`` protocol.  When
        *response_model* is provided the response is still returned as raw
        text (the caller handles parsing).

        Parameters
        ----------
        system_prompt:
            System-level instruction for the LLM.
        messages:
            Conversation history — may be plain dicts ``{"role": ..., "content": ...}``
            or ``Message`` dataclass instances.  Both formats are accepted.
        response_model:
            Ignored for now — kept for protocol compatibility.

        Returns
        -------
        str
            The text response from the LLM.
        """
        normalized: List[Dict[str, str]] = []
        for msg in messages:
            if isinstance(msg, dict):
                normalized.append(msg)
            elif hasattr(msg, "speaker") and hasattr(msg, "content"):
                normalized.append({"role": "user", "content": f"[{msg.speaker}] {msg.content}"})
            else:
                normalized.append({"role": "user", "content": str(msg)})
        full_messages: List[Dict[str, str]] = [
            {"role": "system", "content": system_prompt}
        ] + normalized
        temperature = sampling.temperature if sampling is not None else 0.3
        return self.create_chat_completion_messages(
            full_messages,
            max_tokens=8192,
            temperature=temperature,
        )

    def create_chat_completion_messages(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        """Send a full messages list directly to the chat completions endpoint.

        Parameters
        ----------
        messages:
            List of message dicts with ``role`` and ``content`` keys.
        max_tokens:
            Maximum tokens in the response.
        temperature:
            Sampling temperature.

        Returns
        -------
        Response text string.
        """
        payload = {
            "model": self.config.model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = request.Request(
            self.config.chat_completions_url(),
            data=body,
            headers=headers,
            method="POST",
        )

        response_data = self._request_json_with_retry(req, timeout_seconds=self.config.timeout_seconds)

        return self._extract_text(response_data)

    def create_multimodal_chat_completion(
        self,
        system_prompt: str,
        user_prompt: str,
        image_inputs: List[Dict[str, str]],
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str:
        content: List[Dict[str, Any]] = [{"type": "text", "text": user_prompt}]
        for index, item in enumerate(image_inputs, start=1):
            label = str(item.get("label", "")).strip()
            viewpoint = str(item.get("viewpoint", "")).strip()
            image_path = Path(str(item.get("path", "")).strip())
            if label or viewpoint:
                prefix = f"Attached image {index}"
                details = []
                if label:
                    details.append(label)
                if viewpoint:
                    details.append(f"viewpoint={viewpoint}")
                content.append({"type": "text", "text": f"{prefix}: {', '.join(details)}."})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": self._image_path_to_data_url(image_path),
                    },
                }
            )

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        req = request.Request(
            self.config.chat_completions_url(),
            data=body,
            headers=headers,
            method="POST",
        )
        response_data = self._request_json_with_retry(
            req,
            timeout_seconds=max(self.config.timeout_seconds, self.config.multimodal_timeout_seconds),
        )
        return self._extract_text(response_data)

    def get_models(self) -> List[Dict[str, str]]:
        req = request.Request(url=self.config.get_models_url(), method="GET")
        response_data = self._request_json_with_retry(
            req,
            timeout_seconds=max(self.config.timeout_seconds, self.config.multimodal_timeout_seconds),
        )
        items = response_data.get('data', [])
        models = []
        for i in items:
            model = i.get('id', None)
            if model:
                models.append(model)
        return models

    def check_health(self) -> None:
        probe = request.Request(url=self.config.get_models_url(), method="GET")
        self._probe_with_retry(probe)

    def wait_until_available(self) -> None:
        probe = request.Request(self.config.chat_completions_url(), method="GET")
        self._probe_with_retry(probe)

    def _request_json_with_retry(
        self,
        req: request.Request,
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        effective_timeout = float(timeout_seconds or self.config.timeout_seconds)
        for attempt in range(1, self.config.reconnect_attempts + 1):
            try:
                with request.urlopen(req, timeout=effective_timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                error_body = exc.read().decode("utf-8", errors="replace")
                if exc.code in (502, 503, 504):
                    last_error = RuntimeError(
                        f"Endpoint temporarily unavailable (HTTP {exc.code}): {error_body}"
                    )
                else:
                    raise RuntimeError(f"Endpoint returned HTTP {exc.code}: {error_body}") from exc
            except URLError as exc:
                last_error = RuntimeError(f"Failed to reach LLM endpoint: {exc}")
            except TimeoutError as exc:
                last_error = RuntimeError(
                    f"LLM endpoint timed out after {effective_timeout:.1f}s"
                )

            if attempt < self.config.reconnect_attempts:
                time.sleep(self.config.reconnect_backoff_seconds)

        raise RuntimeError(
            f"LLM endpoint request failed after {self.config.reconnect_attempts} attempts: {last_error}"
        )

    def _probe_with_retry(self, req: request.Request) -> None:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.config.reconnect_attempts + 1):
            try:
                request.urlopen(req, timeout=min(10.0, self.config.timeout_seconds))
                return
            except HTTPError as exc:
                if exc.code in (400, 404, 405):
                    return
                last_error = RuntimeError(f"Endpoint probe failed with HTTP {exc.code}")
            except URLError as exc:
                last_error = RuntimeError(f"Failed to reach LLM endpoint: {exc}")

            if attempt < self.config.reconnect_attempts:
                time.sleep(self.config.reconnect_backoff_seconds)

        raise RuntimeError(
            f"LLM endpoint was unavailable after {self.config.reconnect_attempts} attempts: {last_error}"
        )

    @staticmethod
    def _image_path_to_data_url(image_path: Path) -> str:
        if not image_path.exists():
            raise RuntimeError(f"Image input does not exist: {image_path}")
        mime_type, _ = mimetypes.guess_type(str(image_path))
        if not mime_type:
            mime_type = "image/png"
        encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
        return f"data:{mime_type};base64,{encoded}"

    @staticmethod
    def _extract_text(response_data: Dict[str, Any]) -> str:
        choices = response_data.get("choices", [])
        if not choices:
            return ""

        first_choice = choices[0]
        message = first_choice.get("message")
        if isinstance(message, dict):
            return str(message.get("content", ""))
        return str(first_choice.get("text", ""))
