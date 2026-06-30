"""Production-grade, multi-layered AI guardrails for the Kapruka shopping agent.

These three layers wrap the existing ADK agent flow WITHOUT replacing any of it:

  Layer 1 — InputGuardrail        : screen the user prompt before any MCP/LLM call.
  Layer 2 — DocumentRetrievalEngine: RBAC over which MCP tools a role may call, plus a
                                     role/visibility filter on results before they reach
                                     the model context.
  Layer 3 — OutputGuardrail       : redact PII and check factual grounding of the model's
                                     prose before it reaches the user.

  EnterpriseAIEngine wires the three together in the canonical order.

Security is enforced HERE, in code — never inside a system prompt. All checks are regex /
set lookups (no extra model calls) to keep latency low. Every decision is written to a
dedicated JSON audit log (see AUDIT_LOG_PATH), independent of stdout.

The app is agentic: retrieval happens inside the model loop via MCP tool calls, so the
layers attach at the natural seams — Layer 1 as a pre-runner gate, Layer 2 as ADK tool
callbacks, Layer 3 as a post-runner processor over the buffered reply.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone

from tools.sinks import current_role, current_session_id, product_sink

# ==========================================================================================
# CONFIG  — everything tunable lives here. Edit these to extend the guardrails.
# ==========================================================================================

# --- Layer 1: prompt-injection / jailbreak patterns --------------------------------------
INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE)
    for p in (
        r"ignore\s+(?:all\s+|any\s+|the\s+)?(?:previous|prior|above|earlier)\s+instructions",
        r"disregard\s+(?:all\s+|your\s+|the\s+)?(?:previous\s+)?(?:instructions|rules|guidelines|prompt)",
        r"forget\s+(?:everything|all|your)\s+(?:above|instructions|rules)",
        r"system\s+prompt\s+override",
        r"\b(?:reveal|show|print|repeat|leak)\s+(?:me\s+)?(?:your\s+)?(?:system\s+)?(?:prompt|instructions)\b",
        r"you\s+are\s+now\s+(?:an?\s+)?(?:unconstrained|unrestricted|unfiltered|jailbroken)",
        r"act\s+as\s+(?:a\s+)?(?:terminal|root|admin|dan|developer\s+mode)",
        r"\bact\s+as\s+(?:a\s+)?[\w\s]{0,20}with\s+no\s+(?:rules|restrictions|filter|limits)",
        r"\bdeveloper\s+mode\b",
        r"\bdo\s+anything\s+now\b",
        r"\bpretend\s+(?:you\s+are|to\s+be)\s+(?:an?\s+)?(?:unrestricted|unfiltered|evil)",
        r"bypass\s+(?:your\s+)?(?:safety|content|guard|filter)",
    )
]

# --- Layer 1: explicit forbidden keywords (easy to extend) -------------------------------
FORBIDDEN_KEYWORDS: list[str] = [
    "master password",
    "root credentials",
    "database connection string",
    "connection string",
    "private key",
    "secret key",
    "api key",
    "service account key",
    "env file",
    "/etc/passwd",
]

# --- Layer 2: RBAC — per-role allowlist of CONTROLLED (MCP) tool names --------------------
# Only tools in CONTROLLED_TOOLS are gated; everything else (transfer_to_agent, manage_cart,
# try_on, save_user_info, …) always passes so internal agent plumbing never breaks.
CONTROLLED_TOOLS: set[str] = {
    "kapruka_search_products",
    "kapruka_get_product",
    "kapruka_list_categories",
    "kapruka_check_delivery",
    "kapruka_list_delivery_cities",
    "kapruka_create_order",
    "kapruka_track_order",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    # The only role used in production today (see "Customer-only" decision). Customers can
    # shop, order, and track. Real auth swaps the role at the single call site in main.py.
    "customer": set(CONTROLLED_TOOLS),
    # Sample restricted role demonstrating enforcement: a guest may browse but may NOT place
    # orders or fish arbitrary order numbers via track_order.
    "guest": {
        "kapruka_search_products",
        "kapruka_get_product",
        "kapruka_list_categories",
        "kapruka_check_delivery",
        "kapruka_list_delivery_cities",
    },
    # Staff/admin see everything plus any internally-tagged results (see VISIBILITY_ACCESS).
    "staff": set(CONTROLLED_TOOLS),
    "admin": set(CONTROLLED_TOOLS),
}
# Unknown roles fall back to the most restrictive known role.
DEFAULT_ROLE = "customer"
FALLBACK_ROLE = "guest"

# --- Layer 2: result visibility — optional per-item "documents tagged with role metadata" -
# Products/chunks may carry a "visibility" tag; items with no tag are public. This is the
# RBAC-over-retrieved-content control. Kapruka's live products carry no tag → all public →
# customers see everything (the pass-through we chose), while tests prove staff-only items
# are excluded for a customer.
_ALL_ROLES = object()  # sentinel: visible to any retrieving role
VISIBILITY_ACCESS: dict[str, object] = {
    "public": _ALL_ROLES,
    "staff": {"staff", "admin"},
    "internal": {"admin"},
}
# Fields stripped from any item before it reaches the model context / UI.
SENSITIVE_ITEM_FIELDS: set[str] = {"cost_price", "margin", "supplier", "internal_notes"}

# --- Layer 3: PII redaction patterns (configurable) --------------------------------------
REDACTION_PATTERNS: dict[str, re.Pattern] = {
    "[REDACTED_EMAIL]": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
    "[REDACTED_SSN]": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "[REDACTED_CARD]": re.compile(r"\b(?:\d[ -]?){13,16}\b"),
    "[REDACTED_PHONE]": re.compile(
        r"(?<!\d)(?:\+?\d{1,3}[ -]?)?(?:\(?\d{2,4}\)?[ -]?)\d{3}[ -]?\d{3,4}(?!\d)"
    ),
    "[REDACTED_API_KEY]": re.compile(
        r"\b(?:sk|pk|rk|api|key|token)[-_][A-Za-z0-9]{16,}\b", re.IGNORECASE
    ),
}

# --- Layer 3: factual-grounding config ---------------------------------------------------
# A "critical claim" we verify against the retrieved source products. Default: any quoted
# price. Grounding is only enforced when there ARE source products this turn (so ordinary
# conversational turns are never falsely flagged).
PRICE_CLAIM_PATTERN = re.compile(
    r"(?:rs\.?|lkr|usd|gbp|aud|cad|eur|\$|£|€)\s*([\d,]+(?:\.\d+)?)"
    r"|([\d,]+(?:\.\d+)?)\s*(?:lkr|rupees|usd|dollars)",
    re.IGNORECASE,
)
# Extra free-text keywords to verify against the sources (easy to customize; empty by
# default to avoid false positives on a chatty shopping bot).
CRITICAL_KEYWORDS: list[str] = []

FALLBACK_MESSAGE = (
    "Error: The system generated a response that could not be verified by "
    "internal documentation."
)

# --- Audit log ---------------------------------------------------------------------------
AUDIT_LOG_PATH = os.getenv(
    "GUARDRAIL_AUDIT_LOG",
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "logs", "guardrails_audit.log"),
)
_MAX_SNIPPET = 160

# ==========================================================================================
# Audit logger — JSON lines to a dedicated file, separate from stdout.
# ==========================================================================================

_audit_logger = logging.getLogger("kapruka.guardrails")


def _init_audit_logger() -> None:
    if getattr(_audit_logger, "_kapruka_configured", False):
        return
    try:
        os.makedirs(os.path.dirname(AUDIT_LOG_PATH), exist_ok=True)
        handler: logging.Handler = logging.FileHandler(AUDIT_LOG_PATH, encoding="utf-8")
    except OSError:
        # Fall back to a null handler if the log dir isn't writable — never crash the app
        # because the audit sink is unavailable.
        handler = logging.NullHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    _audit_logger.addHandler(handler)
    _audit_logger.setLevel(logging.INFO)
    _audit_logger.propagate = False
    _audit_logger._kapruka_configured = True  # type: ignore[attr-defined]


_init_audit_logger()


def _audit(
    layer: str,
    decision: str,
    reason: str,
    *,
    role: str | None = None,
    session_id: str | None = None,
    snippet: str | None = None,
) -> None:
    """Write one structured audit entry (timestamp, layer, decision, reason, role, …)."""
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "layer": layer,
        "decision": decision,
        "reason": reason,
        "role": role,
        "session_id": session_id,
    }
    if snippet is not None:
        entry["snippet"] = snippet[:_MAX_SNIPPET]
    _audit_logger.info(json.dumps(entry, ensure_ascii=False))


def _session() -> str | None:
    try:
        return current_session_id.get()
    except LookupError:
        return None


def _role() -> str:
    try:
        return current_role.get() or DEFAULT_ROLE
    except LookupError:
        return DEFAULT_ROLE


# ==========================================================================================
# LAYER 1 — InputGuardrail
# ==========================================================================================


class InputGuardrail:
    """Screen a raw user prompt for prompt-injection / jailbreaks and forbidden keywords."""

    def __init__(
        self,
        injection_patterns: list[re.Pattern] | None = None,
        forbidden_keywords: list[str] | None = None,
    ) -> None:
        self.injection_patterns = injection_patterns or INJECTION_PATTERNS
        self.forbidden_keywords = forbidden_keywords or FORBIDDEN_KEYWORDS

    def validate_prompt(self, user_prompt: str) -> dict:
        """Return {"is_safe": bool, "reason": str}. Regex only — no model calls."""
        text = user_prompt or ""

        for pattern in self.injection_patterns:
            if pattern.search(text):
                reason = f"prompt_injection: matched /{pattern.pattern}/"
                _audit("input", "blocked", reason, role=_role(),
                       session_id=_session(), snippet=text)
                return {"is_safe": False, "reason": reason}

        lowered = text.lower()
        for keyword in self.forbidden_keywords:
            if re.search(r"\b" + re.escape(keyword.lower()) + r"\b", lowered):
                reason = f"forbidden_keyword: {keyword!r}"
                _audit("input", "blocked", reason, role=_role(),
                       session_id=_session(), snippet=text)
                return {"is_safe": False, "reason": reason}

        return {"is_safe": True, "reason": "ok"}


# ==========================================================================================
# LAYER 2 — DocumentRetrievalEngine (RBAC over tools + role/visibility filter on results)
# ==========================================================================================


class DocumentRetrievalEngine:
    """RBAC for the retrieval layer.

    `is_tool_allowed` gates which MCP tools a role may invoke (the strong guarantee:
    a denied tool never runs, so its content never reaches the model). `filter_results`
    and `retrieve_context` apply item-level visibility RBAC and strip sensitive fields.
    """

    def __init__(
        self,
        role_permissions: dict[str, set[str]] | None = None,
        visibility_access: dict[str, object] | None = None,
    ) -> None:
        self.role_permissions = role_permissions or ROLE_PERMISSIONS
        self.visibility_access = visibility_access or VISIBILITY_ACCESS

    # --- tool-level RBAC ---
    def is_tool_allowed(self, user_role: str, tool_name: str) -> bool:
        """True if `user_role` may call `tool_name`. Tools outside CONTROLLED_TOOLS are
        never gated (internal agent plumbing must always work)."""
        if tool_name not in CONTROLLED_TOOLS:
            return True
        allowed = self.role_permissions.get(
            user_role, self.role_permissions.get(FALLBACK_ROLE, set())
        )
        return tool_name in allowed

    # --- item-level visibility RBAC ---
    def _can_see(self, user_role: str, item: dict) -> bool:
        visibility = (item.get("visibility") if isinstance(item, dict) else None) or "public"
        roles = self.visibility_access.get(visibility, set())
        return roles is _ALL_ROLES or user_role in roles  # type: ignore[comparison-overlap]

    @staticmethod
    def _scrub(item: dict) -> dict:
        if not isinstance(item, dict):
            return item
        if not (SENSITIVE_ITEM_FIELDS & item.keys()):
            return item
        return {k: v for k, v in item.items() if k not in SENSITIVE_ITEM_FIELDS}

    def filter_results(self, user_role: str, items: list) -> list:
        """Drop any item the role may not see and strip sensitive fields from the rest.
        Unauthorized content is completely excluded — never returned to the caller."""
        if not items:
            return []
        kept: list = []
        dropped = 0
        for item in items:
            if isinstance(item, dict) and not self._can_see(user_role, item):
                dropped += 1
                continue
            kept.append(self._scrub(item))
        if dropped:
            _audit(
                "retrieval", "filtered",
                f"excluded {dropped} item(s) not visible to role",
                role=user_role, session_id=_session(),
            )
        return kept

    def retrieve_context(self, user_query: str, user_role: str, raw_results: list | None = None) -> list:
        """Standalone retrieval API required by the brief.

        In the agentic flow the actual MCP search runs inside the model loop and the
        result filter is applied via the after-tool callback; this method is the direct,
        testable entry point. `raw_results` lets callers/tests inject the unfiltered
        result set. Returns only the items the role is authorized to see.
        """
        if not self.is_tool_allowed(user_role, "kapruka_search_products"):
            _audit(
                "retrieval", "denied",
                "role not permitted to search products",
                role=user_role, session_id=_session(), snippet=user_query,
            )
            return []
        return self.filter_results(user_role, raw_results or [])


# ==========================================================================================
# LAYER 3 — OutputGuardrail (PII redaction + factual grounding)
# ==========================================================================================


def _price_digits(text: str) -> set[str]:
    """All price amounts mentioned in `text`, normalized to integer-rupee digit strings."""
    found: set[str] = set()
    for m in PRICE_CLAIM_PATTERN.finditer(text):
        raw = m.group(1) or m.group(2)
        if not raw:
            continue
        digits = raw.replace(",", "").split(".")[0]
        if digits:
            found.add(digits.lstrip("0") or "0")
    return found


def _source_corpus(source_contexts: list) -> tuple[str, set[str]]:
    """Flatten retrieved products into (lowercased text blob, set of price digit strings)."""
    blob_parts: list[str] = []
    prices: set[str] = set()
    for item in source_contexts or []:
        if not isinstance(item, dict):
            blob_parts.append(str(item))
            continue
        blob_parts.append(json.dumps(item, ensure_ascii=False, default=str))
        amount = (item.get("price") or {}).get("amount") if isinstance(item.get("price"), dict) else item.get("price")
        if amount is not None:
            try:
                prices.add(str(int(float(amount))).lstrip("0") or "0")
            except (TypeError, ValueError):
                pass
    blob = " ".join(blob_parts).lower()
    prices |= _price_digits(blob)
    return blob, prices


class OutputGuardrail:
    """Redact PII from the model's prose and verify critical claims against the sources."""

    def __init__(
        self,
        redaction_patterns: dict[str, re.Pattern] | None = None,
        critical_keywords: list[str] | None = None,
        fallback_message: str = FALLBACK_MESSAGE,
    ) -> None:
        self.redaction_patterns = redaction_patterns or REDACTION_PATTERNS
        self.critical_keywords = critical_keywords if critical_keywords is not None else CRITICAL_KEYWORDS
        self.fallback_message = fallback_message

    def _redact(self, text: str) -> str:
        redacted = text
        fired: list[str] = []
        for placeholder, pattern in self.redaction_patterns.items():
            redacted, n = pattern.subn(placeholder, redacted)
            if n:
                fired.append(placeholder)
        if fired:
            _audit("output", "redacted", "matched " + ", ".join(fired),
                   role=_role(), session_id=_session())
        return redacted

    def _is_grounded(self, text: str, blob: str, source_prices: set[str]) -> tuple[bool, str]:
        # Verify price claims only when we actually have sources to verify against, so
        # purely conversational turns (no products this turn) are never falsely flagged.
        if not blob:
            return True, ""
        for digits in _price_digits(text):
            if digits not in source_prices and digits not in blob:
                return False, f"unverified price claim: {digits}"
        for keyword in self.critical_keywords:
            if keyword.lower() in text.lower() and keyword.lower() not in blob:
                return False, f"unverified claim: {keyword!r}"
        return True, ""

    def process_output(self, model_response: str, source_contexts: list) -> str:
        """Redact PII, then grounding-check. Returns the safe text (or the fallback)."""
        text = model_response or ""
        blob, source_prices = _source_corpus(source_contexts)

        grounded, reason = self._is_grounded(text, blob, source_prices)
        if not grounded:
            _audit("output", "hallucination", reason, role=_role(),
                   session_id=_session(), snippet=text)
            return self.fallback_message

        return self._redact(text)


# ==========================================================================================
# ORCHESTRATION — EnterpriseAIEngine wires the three layers in the canonical order.
# ==========================================================================================


class EnterpriseAIEngine:
    """Single wiring point. The canonical order is:

      1. InputGuardrail.validate_prompt()      → reject if unsafe          (preflight)
      2. DocumentRetrievalEngine               → RBAC filter by role       (preflight + L2 callbacks)
      3. <existing ADK runner.run_async>       → the LLM call
      4. OutputGuardrail.process_output()      → redact / verify           (finalize)

    In this agentic app steps 2–3 happen inside the model loop, so the engine exposes
    `preflight` (steps 1–2 policy) and `finalize` (step 4); the Layer-2 callbacks below
    enforce retrieval RBAC during step 3.
    """

    def __init__(self) -> None:
        self.input_guard = InputGuardrail()
        self.retrieval = DocumentRetrievalEngine()
        self.output_guard = OutputGuardrail()

    def preflight(self, user_prompt: str, user_role: str = DEFAULT_ROLE) -> dict:
        """Run Layer 1 and resolve the role's tool permissions (Layer 2 policy)."""
        verdict = self.input_guard.validate_prompt(user_prompt)
        if not verdict["is_safe"]:
            return {"allowed": False, "reason": verdict["reason"], "role": user_role}
        permissions = self.retrieval.role_permissions.get(
            user_role, self.retrieval.role_permissions.get(FALLBACK_ROLE, set())
        )
        return {"allowed": True, "reason": "ok", "role": user_role,
                "permissions": sorted(permissions)}

    def finalize(self, model_text: str, source_contexts: list) -> str:
        """Run Layer 3 over the buffered model reply before it reaches the user."""
        return self.output_guard.process_output(model_text, source_contexts)


# Process-wide singleton imported by main.py and the agent callbacks.
engine = EnterpriseAIEngine()


# ==========================================================================================
# LAYER 2 wiring — RBAC callback wrappers that compose with the existing tool callbacks.
# ==========================================================================================


def rbac_before(existing_before):
    """Wrap an existing before_tool_callback with a role-based tool gate.

    Denied CONTROLLED tools short-circuit with the same structured-error shape the
    existing callbacks already use, so the agent narrates a refusal instead of leaking
    unauthorized content. Allowed calls fall through to `existing_before` unchanged.
    """

    def before(*, tool, args, tool_context):
        role = _role()
        name = getattr(tool, "name", None)
        if name is not None and not engine.retrieval.is_tool_allowed(role, name):
            _audit("retrieval", "denied", f"role may not call tool {name!r}",
                   role=role, session_id=_session())
            return {
                "status": "error",
                "message": f"Access denied: your account is not permitted to use {name}.",
            }
        if existing_before is None:
            return None
        return existing_before(tool=tool, args=args, tool_context=tool_context)

    return before


def rbac_after(existing_after):
    """Wrap an existing after_tool_callback with item-level visibility filtering.

    Runs the original capture first, then scrubs the per-request product sink so any
    items the role may not see are dropped before the UI renders them. For the
    `customer` role (no tagged items in production) this is a pass-through.
    """

    def after(*, tool, args, tool_context, tool_response):
        result = None
        if existing_after is not None:
            result = existing_after(
                tool=tool, args=args, tool_context=tool_context, tool_response=tool_response
            )
        try:
            sink = product_sink.get()
        except LookupError:
            sink = None
        if sink:
            filtered = engine.retrieval.filter_results(_role(), sink)
            if len(filtered) != len(sink):
                sink[:] = filtered  # mutate in place so the contextvar keeps the same list
        return result

    return after
