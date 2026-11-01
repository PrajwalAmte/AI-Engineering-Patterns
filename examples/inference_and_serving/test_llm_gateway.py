import pytest

from common.fakes import FakeClock
from inference_and_serving.llm_gateway import (
    BudgetExceeded,
    Deployment,
    Gateway,
    GatewayError,
    RateLimited,
    Team,
    Unauthorized,
)


def down(prompt):
    raise ConnectionError("503 from provider")


def make_gateway(primary=lambda p: "from primary", budget=10.0, rpm=100):
    clock = FakeClock()
    gateway = Gateway(
        routes={
            "chat-default": [
                Deployment("provider-a/large", primary, usd_per_1k_tokens=10.0),
                Deployment("provider-b/large", lambda p: "from backup", usd_per_1k_tokens=12.0),
            ]
        },
        keys={"sk-search": Team("search", monthly_budget_usd=budget, requests_per_minute=rpm)},
        clock=clock,
    )
    return gateway, clock


def test_callers_use_an_alias_and_never_see_provider_keys():
    gateway, _ = make_gateway()
    assert gateway.complete("sk-search", "chat-default", "hello") == "from primary"


def test_unknown_key_is_rejected():
    gateway, _ = make_gateway()
    with pytest.raises(Unauthorized):
        gateway.complete("sk-stolen", "chat-default", "hello")


def test_falls_over_to_next_deployment_and_logs_the_failure():
    gateway, _ = make_gateway(primary=down)
    assert gateway.complete("sk-search", "chat-default", "hello") == "from backup"
    assert [r.deployment for r in gateway.log] == ["provider-a/large", "provider-b/large"]
    assert gateway.log[0].error == "503 from provider"


def test_raises_when_every_deployment_fails():
    gateway, _ = make_gateway()
    gateway.routes["chat-default"] = [Deployment("a", down, 1.0)]
    with pytest.raises(GatewayError, match="all deployments"):
        gateway.complete("sk-search", "chat-default", "hello")


def test_rate_limit_is_per_team_and_resets_each_minute():
    gateway, clock = make_gateway(rpm=2)
    gateway.complete("sk-search", "chat-default", "1")
    gateway.complete("sk-search", "chat-default", "2")
    with pytest.raises(RateLimited):
        gateway.complete("sk-search", "chat-default", "3")
    clock.advance(60)
    assert gateway.complete("sk-search", "chat-default", "4") == "from primary"


def test_budget_cap_stops_spend_and_cost_is_attributed():
    gateway, _ = make_gateway(budget=0.01)
    gateway.complete("sk-search", "chat-default", "x " * 200)
    assert gateway.spend_by_team()["search"] > 0.01
    with pytest.raises(BudgetExceeded):
        gateway.complete("sk-search", "chat-default", "one more")


def test_logs_store_a_hash_not_the_prompt():
    gateway, _ = make_gateway()
    gateway.complete("sk-search", "chat-default", "my SSN is 123-45-6789")
    assert "123-45-6789" not in repr(gateway.log)
