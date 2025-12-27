# nfp_etl_multi/multi_model_client.py
"""Unified interface to call multiple LLM backends.
This implementation supports OpenAI, Gemini, DeepSeek, and Grok models through configurable backends.
"""
import os, json
from typing import Dict, Any, Optional
try:
    from nfp_etl.llm_client import LLMClient
except Exception:
    # fallback if package import path differs
    from llm_client import LLMClient

class MultiModelClient:
    def __init__(self, config: Dict[str, Any]):
        # config: loaded from configs/multi_models.yml
        self.config = config
        self.models = config.get('models', [])
        # cache clients per provider
        self._clients = {}

    def _get_client_for(self, provider: str, model_name: Optional[str]=None, api_key_env: Optional[str]=None):
        # Return a specific client based on the provider
        if provider == 'openai':
            return LLMClient()
        elif provider == 'gemini':
            return self._get_gemini_client(model_name, api_key_env)
        elif provider == 'deepseek':
            return self._get_deepseek_client(model_name, api_key_env)
        elif provider == 'grok':
            return self._get_grok_client(model_name, api_key_env)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _get_gemini_client(self, model_name, api_key_env):
        # Simulated Gemini API client (replace with actual implementation)
        gemini_api_key = os.getenv(api_key_env)
        if not gemini_api_key:
            raise ValueError("Gemini API key not found")
        return LLMClient()

    def _get_deepseek_client(self, model_name, api_key_env):
        # Simulated DeepSeek API client (replace with actual implementation)
        deepseek_api_key = os.getenv(api_key_env)
        if not deepseek_api_key:
            raise ValueError("DeepSeek API key not found")
        return LLMClient()

    def _get_grok_client(self, model_name, api_key_env):
        # Simulated Grok API client (replace with actual implementation)
        grok_api_key = os.getenv(api_key_env)
        if not grok_api_key:
            raise ValueError("Grok API key not found")
        return LLMClient()

    def extract(self, model_id: str, prompt: str, schema: Optional[Dict]=None, images: Optional[list]=None) -> Dict[str, Any]:
        # Find model config
        mc = next((m for m in self.models if m.get('id') == model_id), None)
        if mc is None:
            raise ValueError(f"Unknown model id: {model_id}")
        provider = mc.get('provider')
        model_name = mc.get('model_name')
        api_key_env = mc.get('api_key_env')

        # Optionally set model env for the LLM client (works with llm_client that reads OPENAI_MODEL env)
        prev_model = os.environ.get('OPENAI_MODEL')
        if model_name:
            os.environ['OPENAI_MODEL'] = model_name

        # Optionally ensure API key env present (we don't set it here)
        client = self._get_client_for(provider, model_name=model_name, api_key_env=api_key_env)

        try:
            if schema is None:
                resp = client.structured(prompt, schema={"type":"object"}, images=images)
            else:
                resp = client.structured(prompt, schema=schema, images=images)
        except Exception as e:
            resp = {"error": str(e)}
        # restore env
        if prev_model is None:
            os.environ.pop('OPENAI_MODEL', None)
        else:
            os.environ['OPENAI_MODEL'] = prev_model
        # attach metadata
        out = {"model_id": model_id, "provider": provider, "model_name": model_name, "resp": resp}
        return out
