
# etl_ensemble/llm_openai_client.py
import os, json
from typing import Any, Dict, List, Optional

# --- 自动加载 configs/api_keys.json ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "configs", "api_keys.json")
if os.path.exists(CONFIG_PATH):
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = cfg["OPENAI_API_KEY"]
        if cfg.get("OPENAI_MODEL"):
            os.environ["OPENAI_MODEL"] = cfg["OPENAI_MODEL"]
    except Exception as e:
        raise RuntimeError(f"Failed to read configs/api_keys.json: {e}")
else:
    # 硬性要求存在配置文件
    raise RuntimeError("configs/api_keys.json not found. Please create it with OPENAI_API_KEY and OPENAI_MODEL.")

def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception:
        return None

openai_pkg = _safe_import("openai")

DEFAULT_MODEL = os.getenv("OPENAI_MODEL")  # 必须存在
DEFAULT_KEY = os.getenv("OPENAI_API_KEY")  # 必须存在
if not DEFAULT_KEY or not DEFAULT_MODEL:
    raise RuntimeError("OPENAI_API_KEY or OPENAI_MODEL is missing. Please set them in configs/api_keys.json.")

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
