---
title: Getting Started
description: What this library is, how a pattern page is laid out, and how to run any pattern's code in under a minute.
---

AI Engineering Patterns is a catalog of the techniques teams use to put LLM features into production and keep them there: caching, routing, guardrails, evals, agent loops and more. Each pattern explains the problem, the mechanism, when *not* to use it, and how it fails, and each one comes with a **runnable, tested reference implementation**.

## Run any pattern in under a minute

All examples are plain Python 3.10+ with no dependencies beyond `pytest`. They use deterministic fake models, so you don't need an API key.

```bash
git clone https://github.com/PrajwalAmte/AI-Engineering-Patterns
cd AI-Engineering-Patterns/examples
pip install pytest
pytest                                         # all patterns
pytest reliability/test_circuit_breaker.py     # just one
```

The code on each pattern page is copied from these files by a script, and CI fails if the two drift apart. The code you read is the code that was tested.

To use a pattern with a real model, pass your client where the example takes `llm` or `embed`. Every example takes plain callables for this reason.

## Find the pattern you need

- **You have a specific problem** ("our bill is too high", "RAG answers are wrong", "the agent never stops"): start with the [Decision Guide](decision-guide.md).
- **You want to browse:** patterns are grouped into ten pillars on the [patterns page](/patterns/). The [pattern graph](/graph/) shows how they connect.
- **You want to see patterns working together:** the [case studies](/case-studies/) show how several patterns combine in real products.

## How a pattern page is organized

| Section | What you get |
|---|---|
| What It Is | The idea in a paragraph, and where it came from if it isn't new |
| The Problem It Solves | A concrete scenario of what goes wrong without it |
| How It Works | A diagram and the steps |
| When to Use It | The conditions where it pays off |
| **When NOT to Use It** | The cases where it's the wrong tool. Read this first. |
| Trade-offs | What it costs you |
| Failure Modes | How it breaks *even when implemented correctly* |
| Implementation Example | The tested reference code, plus the command to run its tests |
| Tool Landscape | Products and libraries that implement it |
| Related Patterns / Further Reading | Where to go next, with primary sources |

## Status labels

- **Validated in production:** widely used by many teams, and the trade-offs are well understood.
- **Emerging:** used by early adopters. The idea is sound, but expect best practice to change.
- **Proposed:** a promising idea without much production evidence yet.

Some pattern names are established terms (Circuit Breaker, LLM-as-Judge). Others are names we use for a technique that teams practice without a common name (Retrieval Freshness Watermark, Tool Output Firewall). The page says which.

## Contributing

Corrections, production stories and new patterns are welcome. A new pattern needs a runnable example with tests. See the [Contributing Guide](../../CONTRIBUTING.md).
