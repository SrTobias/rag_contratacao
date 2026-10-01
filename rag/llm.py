"""Cliente LLM com interface única para servidores OpenAI-compatíveis (Ollama, vLLM) e Azure OpenAI."""
from __future__ import annotations

from typing import Iterator, List, Dict

from .config import Settings

Messages = List[Dict[str, str]]


class LLM:
    def __init__(self, settings: Settings):
        self.settings = settings
        if settings.llm_provider == "azure_openai":
            from openai import AzureOpenAI

            self.client = AzureOpenAI(
                azure_endpoint=settings.llm_base_url,
                api_key=settings.llm_api_key,
                api_version=settings.azure_api_version,
            )
        elif settings.llm_provider == "openai_compatible":
            from openai import OpenAI

            self.client = OpenAI(base_url=settings.llm_base_url, api_key=settings.llm_api_key or "none", max_retries=5)
        else:
            raise ValueError(f"LLM_PROVIDER desconhecido: {settings.llm_provider}")

    def _params(self, messages: Messages) -> dict:
        return {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": self.settings.llm_temperature,
            "max_tokens": self.settings.llm_max_tokens,
        }

    def chat(self, messages: Messages) -> str:
        resp = self.client.chat.completions.create(**self._params(messages))
        return resp.choices[0].message.content or ""

    def stream(self, messages: Messages) -> Iterator[str]:
        resp = self.client.chat.completions.create(**self._params(messages), stream=True)
        for event in resp:
            if event.choices and event.choices[0].delta and event.choices[0].delta.content:
                yield event.choices[0].delta.content
