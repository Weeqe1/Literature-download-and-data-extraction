# etl_ensemble/llm_openai_client.py
"""OpenAI LLM client with lazy config loading.

Configuration is loaded on first use rather than at module import time,
avoiding side effects when the module is imported but not used.
"""

import os
import json
import logging
import diskcache
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

cache = diskcache.Cache(".api_cache")

try:
    import yaml
except Exception:
    yaml = None

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "configs", "extraction", "llm_backends.yml")


def _load_openai_config_from_backends():
    """Load OpenAI config from llm_backends.yml.

    Returns:
        Tuple of (api_key, model_name).

    Raises:
        RuntimeError: If config cannot be loaded.
    """
    if yaml is None:
        raise RuntimeError("PyYAML not installed. Please `pip install pyyaml`.")
    if not os.path.exists(CONFIG_PATH):
        raise RuntimeError(f"configs/extraction/llm_backends.yml not found.")
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        models = cfg.get("models", [])
        for m in models:
            if m.get("provider") == "openai":
                api_key = m.get("api_key_env", "")
                model_name = m.get("model_name", "gpt-4o")
                return api_key, model_name
        raise RuntimeError("No OpenAI model found in llm_backends.yml")
    except Exception as e:
        raise RuntimeError(f"Failed to read llm_backends.yml: {e}")


def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None


openai_pkg = _safe_import("openai")


def load_config():
    """Explicitly load and return OpenAI config from backends file.

    Returns:
        Tuple of (api_key, model_name).
    """
    api_key, model_name = _load_openai_config_from_backends()
    if api_key:
        os.environ.setdefault("OPENAI_API_KEY", api_key)
    if model_name:
        os.environ.setdefault("OPENAI_MODEL", model_name)
    logger.info("Loaded OpenAI config: model=%s", model_name)
    return api_key, model_name


class LLMClient:
    """OpenAI-compatible LLM client with lazy config loading.

    If api_key/model are not provided at construction time, they are
    loaded from the llm_backends.yml configuration file on first use.
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None,
                 base_url: Optional[str] = None):
        # Lazy load config if not provided
        if not api_key or not model:
            try:
                loaded_key, loaded_model = _load_openai_config_from_backends()
                api_key = api_key or loaded_key
                model = model or loaded_model
            except Exception as e:
                logger.warning("Could not load OpenAI config from backends: %s", e)

        self.api_key = api_key
        self.model = model
        self.base_url = base_url

        if not openai_pkg:
            raise RuntimeError("openai package not installed. Please `pip install openai>=1.25`.")
        if not self.api_key or not self.model:
            raise RuntimeError("OPENAI_API_KEY or OPENAI_MODEL is missing. Please configure OpenAI in configs/extraction/llm_backends.yml.")

        try:
            from openai import OpenAI
            # MiMo uses 'api-key' header instead of 'Authorization: Bearer'
            if base_url and "xiaomimomo.com" in base_url:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url,
                                     default_headers={"api-key": self.api_key})
            else:
                self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}")
        # Detect supported mode
        self.support_responses = hasattr(self.client, "responses") and hasattr(self.client.responses, "create")

    def _responses_structured(self, prompt: str, schema: Dict[str, Any], images: Optional[List[str]]) -> Dict[str, Any]:
        input_items = [{"role": "user", "content": prompt}]
        if images:
            for url in images:
                input_items.append({"role": "user", "content": [{"type": "input_image", "image_url": url}]})
        try:
            resp = self.client.responses.create(
                model=self.model,
                input=input_items,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "nfp_schema", "schema": schema or {"type": "object"}, "strict": True}
                }
            )
        except TypeError as e:
            raise e
        except Exception as e:
            raise RuntimeError(f"Responses API request failed: {e}")
        # Parse text
        txt = getattr(resp, "output_text", None)
        if not txt:
            try:
                outputs = getattr(resp, "output", None) or getattr(resp, "outputs", None)
                if outputs and getattr(outputs[0], "content", None) and hasattr(outputs[0].content[0], "text"):
                    txt = outputs[0].content[0].text
            except Exception:
                pass
        if not txt:
            raise RuntimeError("Responses API returned no text content.")
        try:
            return json.loads(txt)
        except Exception as e:
            raise RuntimeError(f"Failed to parse JSON from Responses API: {e}; raw={txt[:200]}")

    def _chat_json_mode(self, prompt: str, schema: Dict[str, Any], images: Optional[List[str]]) -> Dict[str, Any]:
        from openai import OpenAI
        chat_client = self.client or OpenAI(api_key=self.api_key)
        sys_msg = (
            "You are a structured information extractor. "
            "Return ONLY valid JSON. Follow the provided schema keys/types as much as possible. "
            "Unknown fields should be null."
        )
        user_content: List[Any] = [{"type": "text", "text": prompt}]
        if images:
            for url in images:
                user_content.append({"type": "image_url", "image_url": {"url": url}})
        try:
            resp = chat_client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": sys_msg + "\nSchema:\n" + json.dumps(schema or {"type": "object"})},
                    {"role": "user", "content": user_content}
                ],
                response_format={"type": "json_object"}
            )
            txt = resp.choices[0].message.content
            return json.loads(txt)
        except Exception as e:
            raise RuntimeError(f"Chat Completions JSON mode failed: {e}")

    def structured(self, prompt: str, schema: Dict[str, Any], images: Optional[List[str]] = None) -> Dict[str, Any]:
        if self.support_responses:
            try:
                return self._responses_structured(prompt, schema, images)
            except TypeError:
                return self._chat_json_mode(prompt, schema, images)
        return self._chat_json_mode(prompt, schema, images)
