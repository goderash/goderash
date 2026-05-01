"""Pre-LLM fraud guard.

Scans the **user message** (and optionally the LLM's planned tool args) for
prompt-injection markers, secret-leak patterns, and social-engineering
phrasing. Returns a verdict; explicit deny short-circuits the chain.

Patterns are intentionally conservative — we err on the side of false
positives in regulated contexts. Tune via `extra_reject_patterns` per
deployment.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from ..client import GoderashClient, GoderashContext
from .chain import GuardDecision

Verdict = Literal["allow", "warn", "reject"]


@dataclass(frozen=True)
class FraudVerdict:
    verdict: Verdict
    reasons: tuple[str, ...]
    matched_patterns: tuple[str, ...]


# These are the patterns Dashen AIR's `fraud_guard.py` emits with explicit
# regex. We keep names stable so audit reports stay consistent across
# tenants.
_REJECT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("prompt_injection_ignore_instructions",
     re.compile(r"\bignore\s+(all\s+)?(previous|prior|above)\s+instructions?\b", re.I)),
    ("prompt_injection_system_prompt_leak",
     re.compile(r"\b(reveal|show|print|return)\s+(your\s+)?system\s+prompt\b", re.I)),
    ("seed_phrase_share",
     re.compile(r"\b(seed|recovery)\s+phrase\b|\b(12|24)\s*words?\b\s*(?:seed|wallet)?", re.I)),
    ("otp_share",
     re.compile(r"\b(send|share|tell|give)\s+(?:(?:me|the|your)\s+)*(otp|one[\- ]time|2fa|verification)\s+code\b",
                re.I)),
    ("pin_share",
     re.compile(r"\b(send|share|tell|give)\s+(?:(?:me|the|your)\s+)*(pin|password)\b", re.I)),
    ("api_key_share",
     re.compile(r"\b(send|share|paste)\s+(?:(?:me|the|your)\s+)*(api\s+key|secret\s+key|access\s+token)\b",
                re.I)),
    ("private_key_leak",
     re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |)PRIVATE KEY-----")),
]


_WARN_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("urgency_pressure",
     re.compile(r"\b(urgent|right\s+now|immediately|asap|emergency)\b", re.I)),
    ("authority_impersonation",
     re.compile(r"\b(this\s+is\s+(your|the)\s+(ceo|cfo|admin|support|bank|irs|ssn))\b", re.I)),
    ("unusual_recipient",
     re.compile(r"\b(?:wire|transfer|send)\s+(?:money|funds|payment)\s+to\s+\w+@\w+", re.I)),
]


@dataclass
class FraudGuard:
    extra_reject_patterns: list[tuple[str, re.Pattern[str]]] = field(default_factory=list)
    extra_warn_patterns: list[tuple[str, re.Pattern[str]]] = field(default_factory=list)

    def scan(self, text: str) -> FraudVerdict:
        if not text:
            return FraudVerdict("allow", reasons=(), matched_patterns=())

        rejects: list[str] = []
        for name, pat in _REJECT_PATTERNS + self.extra_reject_patterns:
            if pat.search(text):
                rejects.append(name)
        if rejects:
            return FraudVerdict("reject", reasons=tuple(rejects), matched_patterns=tuple(rejects))

        warns: list[str] = []
        for name, pat in _WARN_PATTERNS + self.extra_warn_patterns:
            if pat.search(text):
                warns.append(name)
        if warns:
            return FraudVerdict("warn", reasons=tuple(warns), matched_patterns=tuple(warns))

        return FraudVerdict("allow", reasons=(), matched_patterns=())

    def evaluate(
        self,
        client: GoderashClient,
        ctx: GoderashContext,
        *,
        tool_name: str,
        user_message: str = "",
        **_: Any,
    ) -> GuardDecision:
        verdict = self.scan(user_message)
        if verdict.verdict == "reject":
            return GuardDecision.deny(
                "fraud_guard",
                f"fraud_guard rejected: {','.join(verdict.reasons)}",
                details={"matched": list(verdict.matched_patterns)},
            )
        # `warn` does not deny — the agent can proceed but the warning is
        # captured in the ledger via the GuardChain at the granted side.
        return GuardDecision.grant(
            "rule",
            reason=("fraud_guard:warn:" + ",".join(verdict.reasons)) if verdict.reasons else None,
        )
