# etl_ensemble/llm_multi_client.py
"""Unified interface to call multiple LLM backends.
This implementation supports OpenAI, Gemini, DeepSeek, and Grok models through configurable backends.
"""
import os, json
from typing import Dict, Any, Optional
try:
    from .llm_openai_client import LLMClient
except Exception:
    # fallback if package import path differs
    from llm_openai_client import LLMClient

class MultiModelClient:
    def __init__(self, config: Dict[str, Any]):
        # config: loaded from configs/multi_models.yml
        self.config = config
        self.models = config.get('models', [])
        # cache clients per provider
        self._clients = {}

    def _get_api_key(self, api_key_val: Optional[str]) -> Optional[str]:
        """优先判断是否是 API Key，如果看起来像环境变量名则从环境读取"""
        if not api_key_val:
            return None
        # 简单的启发式判断：如果包含横杠或长度较长，且不全是全大写+下划线，则视为 Key
        # 或者直接尝试读取环境变量，如果读取不到则视为 Key 本身
        env_val = os.getenv(api_key_val)
        if env_val:
            return env_val
        return api_key_val

    def _get_client_for(self, provider: str, model_name: Optional[str]=None, api_key_env: Optional[str]=None):
        api_key = self._get_api_key(api_key_env)
        
        if provider == 'openai':
            return LLMClient(api_key=api_key, model=model_name)
        elif provider == 'gemini':
            if not api_key:
                raise ValueError("Gemini API key not found in config or env")
            # Gemini 可以通过 Google 提供的 OpenAI 兼容网关调用
            # 或者是如果您使用的是某些第三方转发，可以在此处设置 base_url
            # 目前暂时抛出异常或设置标准 OpenAI 客户端（如果用户配置了兼容地址）
            return LLMClient(api_key=api_key, model=model_name, base_url="https://generativelanguage.googleapis.com/v1beta/openai/")
        elif provider == 'deepseek':
            if not api_key:
                raise ValueError("DeepSeek API key not found in config or env")
            return LLMClient(api_key=api_key, model=model_name, base_url="https://api.deepseek.com")
        elif provider == 'grok':
            if not api_key:
                raise ValueError("Grok API key not found in config or env")
            return LLMClient(api_key=api_key, model=model_name, base_url="https://api.x.ai/v1")
        else:
            raise ValueError(f"Unsupported provider: {provider}")

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
