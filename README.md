# AI Engineering Patterns

**37 production patterns for LLM systems. Every one ships with code you can run and tests that pass.**

Most writing about LLM architecture stops at the diagram. This library doesn't. Each pattern (circuit breakers, semantic caching, guardrails, LLM-as-judge, agent loop termination and 32 more) comes with a small, dependency-free Python reference implementation and a test suite that runs offline in CI. The code on the website is copied from those files automatically, so what you read is what was tested.

[**Browse the patterns →**](https://prajwalamte.github.io/AI-Engineering-Patterns/) · [Decision guide](https://prajwalamte.github.io/AI-Engineering-Patterns/guides/decision-guide/) · [Pattern graph](https://prajwalamte.github.io/AI-Engineering-Patterns/graph/)

```bash
git clone https://github.com/PrajwalAmte/AI-Engineering-Patterns
cd AI-Engineering-Patterns/examples && pip install pytest && pytest
# 200 passed: no API keys, no network, no dependencies
```

## Why another patterns list?

Because the others ask you to trust them. A runnable example with tests is a claim you can check:

- **It works the way the page says.** The circuit breaker test steps through a cooldown. The semantic cache test checks that a different tenant's question isn't served from cache. The guardrail test hangs a moderation call and checks that the request fails closed.
- **The edge cases are tested.** Each example tests the failure the page warns about. Examples: the grounding verifier catches "$59" when the source says "$49", the tool-output firewall can't be escaped with a forged closing tag, and entity resolution won't chain two different companies through a vague record.
- **You can lift it.** Every example takes plain callables (`llm(prompt) -> str`, `embed(text) -> list[float]`), so you can plug in your own client and keep the tests.

Each pattern page also says **when not to use it** and **how it fails even when built correctly**. That's usually the most useful part.

## The patterns

| Pillar | Patterns |
|---|---|
| **Inference & Serving** | LLM Gateway · Model Router · Semantic Caching · Multi-Agent Orchestration |
| **Retrieval & Memory** | Hybrid Search · Retrieval Freshness Watermark · Retrieval Quality Gate · Sliding Context Window · Grounding Verifier |
| **Data** | Data Contract · Semantic Deduplication |
| **Reliability** | Circuit Breaker · Request Hedging · Uncertainty-Triggered Retry |
| **Observability & Evaluation** | Span-Level Tracing · LLM-as-Judge · Embedding Drift Detector · Prompt Mutation Testing · Shadow Model Evaluation |
| **Security & Trust** | Input Sanitization · Tool Output Firewall · Guardrails |
| **Cost & Efficiency** | Token Budget · Cascading Context Assembly · Context Compaction · Effort Scaling |
| **Governance** | Human-in-the-Loop · Prompt Canary Deployment · Model Card |
| **Graph** | GraphRAG · Entity Resolution Graph · Graph of Thoughts |
| **Loop Engineering** | Loop Termination · No-Progress Detection · Maker–Verifier Split · Reflexion Loop · Semantic Rollback |

Not sure where to start? The [decision guide](https://prajwalamte.github.io/AI-Engineering-Patterns/guides/decision-guide/) starts from symptoms ("our bill is too high", "RAG answers are wrong", "the agent never stops") and points you to two or three patterns.

## What a pattern looks like

Every page has the same sections: what it is · the problem · how it works (with a diagram) · when to use it · **when NOT to use it** · trade-offs · **failure modes** · the tested implementation · tools that implement it · related patterns · primary sources.

Status labels are honest. *Validated in production* means widely used. *Emerging* means real but still settling. Where a pattern name is ours rather than an industry term, the page says so.

## Repository layout

```
examples/                   Runnable reference implementations + tests (Python 3.10+, stdlib only)
  common/fakes.py           Deterministic fake LLM, embeddings and clock used by the tests
  <pillar>/<pattern>.py     One module per pattern
  <pillar>/test_<pattern>.py
content/
  patterns/<pillar>/*.md    Pattern pages (code blocks synced from examples/)
  guides/                   Getting started, decision guide, glossary
  case-studies/             How patterns combine in Claude, OpenAI Agents SDK and Perplexity
web/                        Next.js static site (Velite content pipeline, Pagefind search)
scripts/
  sync-examples.js          Copies example code into pattern pages (--check in CI)
  validate-schema.js        Frontmatter, related-pattern names and every internal link
```

CI runs the example tests on Python 3.10 and 3.13, checks that pages are in sync with the examples, validates content and links, and builds the site.

## Run the site locally

```bash
cd web
npm install
npm run dev     # http://localhost:3000
```

## Contributing

Corrections, production war stories and new patterns are all welcome. The bar for a new pattern: a page in the standard format **and** a runnable example with tests. See [CONTRIBUTING.md](CONTRIBUTING.md).

If something here saved you a production incident, a ⭐ helps other engineers find it.

## License

MIT
