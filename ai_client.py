"""
ai_client.py — AI Provider Abstraction Layer
==============================================
MANASK VISEF — Phase 0 AI Deliverable

Cấu trúc:
    AIProvider (ABC)
    ├── ClaudeProvider  — Anthropic API (production)
    └── LocalProvider   — Stub cho local model (Ollama/Qwen, dev only)

    get_ai_provider()   — factory, đọc AI_PROVIDER env var

Spec v1.0 — Invariant 6:
    LLM là một component của product, không phải nguồn sự thật của research metrics.
    Research logic không phụ thuộc vào provider nào.
"""

import os
import json
import re
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# ABSTRACT INTERFACE
# ══════════════════════════════════════════════════════════════════════════════

class AIProvider(ABC):
    """
    Interface chung cho mọi AI provider.
    chatbot.py chỉ gọi methods ở đây — không import anthropic hay ollama trực tiếp.
    """

    @abstractmethod
    def chat(
        self,
        messages: list,
        system: str,
        max_tokens: int = 16000,
    ) -> str:
        """
        Gửi conversation tới model, nhận raw text response.

        Args:
            messages:   List[{"role": "user"|"assistant", "content": str}]
            system:     System prompt (build bởi chatbot.py — chứa user context)
            max_tokens: Giới hạn output tokens

        Returns:
            Raw text string từ model (chưa parse JSON).
            chatbot.py chịu trách nhiệm parse + validate.
        """

    @abstractmethod
    def estimate_difficulty(
        self,
        task_name: str,
        context: str,
        project_name: str = "",
    ) -> int:
        """
        Ước lượng độ khó task trên thang 1–5.

        Args:
            task_name:    Tên task cần ước tính
            context:      Mô tả các task khác trong project (calibration)
            project_name: Tên project để AI có domain context

        Returns:
            int 1–5. Fallback về 3 nếu có lỗi.
        """


# ══════════════════════════════════════════════════════════════════════════════
# CLAUDE PROVIDER — PRODUCTION
# ══════════════════════════════════════════════════════════════════════════════

class ClaudeProvider(AIProvider):
    """
    Anthropic Claude — production AI provider.

    Chat model:     claude-sonnet-4-6   (quality + cost balance)
    Estimate model: claude-haiku-4-5-20251001 (lightweight, đủ cho scoring)
    """

    CHAT_MODEL     = "claude-sonnet-4-6"
    ESTIMATE_MODEL = "claude-haiku-4-5-20251001"

    # System prompt tĩnh cho difficulty estimation.
    # Không phụ thuộc vào user context → lưu ở đây thay vì chatbot.py.
    _DIFFICULTY_SYSTEM = (
        "You are an expert task difficulty estimator embedded in a project management tool.\n\n"
        "Your job: given a task name and its project context, assign a difficulty score from 1 to 5.\n\n"
        "SCALE:\n"
        "1 — Trivial    : Simple lookup, copy-paste, or single-click action. < 30 min.\n"
        "2 — Easy       : Straightforward with a clear single step. 30 min – 2 hrs.\n"
        "3 — Medium     : Requires planning or multiple steps. 2–8 hrs.\n"
        "4 — Hard       : Complex logic, coordination, or significant research. 1–3 days.\n"
        "5 — Very Hard  : High uncertainty, cross-team dependency, or architectural impact. > 3 days.\n\n"
        "SCORING GUIDELINES:\n"
        "- Anchor your estimate to the other tasks in the project. "
        "If most tasks are complex (4–5), a 'write unit test' task is relatively easy (2).\n"
        "- Use time_spent of completed tasks as a calibration signal: longer time = harder.\n"
        "- Prioritise the semantic meaning of the task name over surface length.\n"
        "- 'high' priority tasks tend to be harder, but not always — use it as a weak signal only.\n\n"
        "RESPONSE FORMAT:\n"
        "Respond with ONLY a raw JSON object. No markdown, no explanation.\n"
        '{"estimated_difficulty": <integer 1-5>, "reasoning": "<one sentence>"}'
    )

    def __init__(self, api_key: str):
        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)
        logger.info(
            f"[AI] ClaudeProvider ready — "
            f"chat: {self.CHAT_MODEL} | estimate: {self.ESTIMATE_MODEL}"
        )

    def chat(
        self,
        messages: list,
        system: str,
        max_tokens: int = 16000,
    ) -> str:
        """Gọi Claude API, trả về raw text."""
        response = self._client.messages.create(
            model=self.CHAT_MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=messages,
        )
        raw_text = response.content[0].text.strip()
        logger.debug(f"[AI] Claude response: {len(raw_text)} chars")
        return raw_text

    def estimate_difficulty(
        self,
        task_name: str,
        context: str,
        project_name: str = "",
    ) -> int:
        """Gọi Haiku để score difficulty, parse JSON, fallback về 3."""
        project_line = f"Project: {project_name}\n" if project_name else ""
        has_context  = bool(context and context.strip())

        user_message = (
            f"{project_line}"
            f'Task to estimate: "{task_name}"\n\n'
            f"Other tasks in this project for calibration:\n"
            f"{context.strip() if has_context else '(none — estimate from task name and project name alone)'}"
        )

        try:
            response = self._client.messages.create(
                model=self.ESTIMATE_MODEL,
                max_tokens=120,
                system=self._DIFFICULTY_SYSTEM,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text.strip()
            logger.debug(f"[AI] Difficulty raw: {raw_text}")

            match = re.search(r'\{.*\}', raw_text, re.DOTALL)
            if match:
                data  = json.loads(match.group())
                score = max(1, min(5, int(data.get("estimated_difficulty", 3))))
                logger.info(
                    f"[AI] Difficulty: {score}/5 — {data.get('reasoning', '')}"
                )
                return score

            logger.warning("[AI] Could not parse difficulty JSON — fallback to 3")
            return 3

        except Exception as exc:
            logger.error(f"[AI] estimate_difficulty error: {exc}")
            return 3


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL PROVIDER — STUB (DEV ONLY)
# ══════════════════════════════════════════════════════════════════════════════

class LocalProvider(AIProvider):
    """
    Stub cho local model (Ollama / Qwen).

    Phase 0: chưa implement — tồn tại để interface hoàn chỉnh và
             để sau này implement mà không cần đổi interface.

    Cách dùng (development):
        AI_PROVIDER=local OLLAMA_URL=http://localhost:11434 uvicorn main:app

    Phase 1+: implement Ollama HTTP calls tại đây.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str    = "qwen2.5:7b",
    ):
        self._base_url = base_url
        self._model    = model
        logger.warning(
            f"[AI] LocalProvider initialized (STUB) — {base_url} / {model}. "
            "Mọi API call sẽ raise NotImplementedError. "
            "Set AI_PROVIDER=claude cho production."
        )

    def chat(self, messages: list, system: str, max_tokens: int = 16000) -> str:
        raise NotImplementedError(
            "LocalProvider.chat() chưa được implement trong Phase 0. "
            "Set AI_PROVIDER=claude trong .env để dùng production."
        )

    def estimate_difficulty(
        self, task_name: str, context: str, project_name: str = ""
    ) -> int:
        raise NotImplementedError(
            "LocalProvider.estimate_difficulty() chưa được implement trong Phase 0."
        )


# ══════════════════════════════════════════════════════════════════════════════
# FACTORY
# ══════════════════════════════════════════════════════════════════════════════

def get_ai_provider() -> AIProvider:
    """
    Factory function — đọc env var AI_PROVIDER và trả về provider tương ứng.

    Env vars:
        AI_PROVIDER   = "claude" (default) | "local"
        ANTHROPIC_API_KEY — bắt buộc khi AI_PROVIDER=claude
        OLLAMA_URL    = "http://localhost:11434" (chỉ khi AI_PROVIDER=local)
        LOCAL_MODEL   = "qwen2.5:7b"            (chỉ khi AI_PROVIDER=local)

    Nên gọi một lần và giữ kết quả như singleton ở module level.
    Không gọi lại mỗi request.
    """
    name = os.getenv("AI_PROVIDER", "claude").strip().lower()

    if name == "local":
        base_url = os.getenv("OLLAMA_URL",  "http://localhost:11434")
        model    = os.getenv("LOCAL_MODEL", "qwen2.5:7b")
        return LocalProvider(base_url=base_url, model=model)

    # Default: Claude
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "ANTHROPIC_API_KEY không được set. "
            "Thêm vào .env file hoặc set AI_PROVIDER=local để dev offline."
        )
    return ClaudeProvider(api_key=api_key)
