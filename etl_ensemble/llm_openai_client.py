
# etl_ensemble/llm_openai_client.py
import os, json
from typing import Any, Dict, List, Optional

# --- 自动加载 configs/extraction/llm_backends.yml 中的 OpenAI 配置 ---
try:
    import yaml
except Exception:
    yaml = None

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "configs", "extraction", "llm_backends.yml")

def _load_openai_config_from_backends():
    """从 llm_backends.yml 中提取 OpenAI 配置"""
    if yaml is None:
        raise RuntimeError("PyYAML not installed. Please `pip install pyyaml`.")
    if not os.path.exists(CONFIG_PATH):
        raise RuntimeError(f"configs/extraction/llm_backends.yml not found.")
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        models = cfg.get("models", [])
        # 查找 OpenAI 配置
        for m in models:
            if m.get("provider") == "openai":
                api_key = m.get("api_key_env", "")
                model_name = m.get("model_name", "gpt-4o")
                return api_key, model_name
        raise RuntimeError("No OpenAI model found in llm_backends.yml")
    except Exception as e:
        raise RuntimeError(f"Failed to read llm_backends.yml: {e}")

# 加载配置
_api_key, _model_name = _load_openai_config_from_backends()
if _api_key:
    os.environ["OPENAI_API_KEY"] = _api_key
if _model_name:
    os.environ["OPENAI_MODEL"] = _model_name

def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None

openai_pkg = _safe_import("openai")

DEFAULT_MODEL = os.getenv("OPENAI_MODEL")
DEFAULT_KEY = os.getenv("OPENAI_API_KEY")
if not DEFAULT_KEY or not DEFAULT_MODEL:
    raise RuntimeError("OPENAI_API_KEY or OPENAI_MODEL is missing. Please configure OpenAI in configs/extraction/llm_backends.yml.")

class LLMClient:
    """
    强制要求可用的大模型：
    - 若 OpenAI SDK 不可用、密钥/模型缺失或网络异常，均抛出 RuntimeError 阻止流水线继续。
    - 优先尝试 Responses API 的结构化输出；若 SDK 不支持，再使用 Chat Completions 的 JSON 模式；两者若失败即报错。
    """
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or DEFAULT_KEY
        self.model = model or DEFAULT_MODEL
        if not openai_pkg:
            raise RuntimeError("openai package not installed. Please `pip install openai>=1.25`.")
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize OpenAI client: {e}")
        # 探测支持模式
        self.support_responses = hasattr(self.client, "responses") and hasattr(self.client.responses, "create")

    def _responses_structured(self, prompt: str, schema: Dict[str, Any], images: Optional[List[str]]) -> Dict[str, Any]:
        input_items = [{"role": "user", "content": prompt}]
        if images:
            for url in images:
                input_items.append({"role": "user", "content": [{"type":"input_image","image_url": url}]})
        try:
            resp = self.client.responses.create(
                model=self.model,
                input=input_items,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "nfp_schema", "schema": schema or {"type":"object"}, "strict": True}
                }
            )
        except TypeError as e:
            # SDK 不支持 response_format
            raise e
        except Exception as e:
            raise RuntimeError(f"Responses API request failed: {e}")
        # 解析文本
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
                    {"role": "system", "content": sys_msg + "\nSchema:\n" + json.dumps(schema or {"type":"object"})},
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
                # 回退到 Chat JSON 模式
                return self._chat_json_mode(prompt, schema, images)
        # 无 Responses，直接用 Chat JSON
        return self._chat_json_mode(prompt, schema, images)
