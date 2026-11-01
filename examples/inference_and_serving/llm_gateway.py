"""LLM Gateway.

One place where every model call is authenticated, budgeted, routed, retried
and logged. Callers ask for a model *alias* ("chat-default"); the gateway
decides which provider deployment serves it.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass, field

Provider = Callable[[str], str]


class GatewayError(Exception):
    pass


class Unauthorized(GatewayError):
    pass


class RateLimited(GatewayError):
    pass


class BudgetExceeded(GatewayError):
    pass


@dataclass
class Deployment:
    name: str
    call: Provider
    usd_per_1k_tokens: float


@dataclass
class Team:
    name: str
    monthly_budget_usd: float
    requests_per_minute: int
    spent_usd: float = 0.0
    _window_start: float = 0.0
    _window_count: int = 0


@dataclass
class LogRecord:
    team: str
    alias: str
    deployment: str | None
    prompt_sha256: str  # hash, not the prompt: full payloads belong in sampled storage
    tokens: int
    cost_usd: float
    latency_s: float
    error: str | None = None


@dataclass
class Gateway:
    routes: dict[str, list[Deployment]]  # alias -> deployments in fallback order
    keys: dict[str, Team]  # virtual API key -> team
    clock: Callable[[], float] = time.monotonic
    count_tokens: Callable[[str], int] = lambda text: max(1, len(text) // 4)
    log: list[LogRecord] = field(default_factory=list)

    def complete(self, api_key: str, alias: str, prompt: str) -> str:
        team = self.keys.get(api_key)
        if team is None:
            raise Unauthorized("unknown API key")
        self._check_rate_limit(team)
        if team.spent_usd >= team.monthly_budget_usd:
            raise BudgetExceeded(f"{team.name} has spent its ${team.monthly_budget_usd:.2f} budget")
        if alias not in self.routes:
            raise GatewayError(f"unknown model alias {alias!r}")

        prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
        last_error = None
        for deployment in self.routes[alias]:
            start = self.clock()
            try:
                text = deployment.call(prompt)
            except Exception as exc:  # provider-specific errors stay behind the gateway
                last_error = f"{deployment.name}: {exc}"
                self.log.append(LogRecord(team.name, alias, deployment.name, prompt_hash, 0, 0.0,
                                          self.clock() - start, error=str(exc)))
                continue

            tokens = self.count_tokens(prompt) + self.count_tokens(text)
            cost = tokens / 1000 * deployment.usd_per_1k_tokens
            team.spent_usd += cost
            self.log.append(LogRecord(team.name, alias, deployment.name, prompt_hash, tokens, cost,
                                      self.clock() - start))
            return text

        raise GatewayError(f"all deployments for {alias!r} failed; last error: {last_error}")

    def _check_rate_limit(self, team: Team) -> None:
        now = self.clock()
        if now - team._window_start >= 60:
            team._window_start, team._window_count = now, 0
        if team._window_count >= team.requests_per_minute:
            raise RateLimited(f"{team.name} exceeded {team.requests_per_minute} requests/minute")
        team._window_count += 1

    def spend_by_team(self) -> dict[str, float]:
        totals: dict[str, float] = {}
        for record in self.log:
            totals[record.team] = totals.get(record.team, 0.0) + record.cost_usd
        return totals
