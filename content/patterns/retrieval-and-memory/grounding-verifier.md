---
title: Grounding Verifier
pillar: retrieval-and-memory
status: emerging
tags: [rag, grounding, hallucination, verification, citations]
related:
  - Retrieval Quality Gate
  - Hybrid Search
  - LLM-as-Judge
  - Retrieval Freshness Watermark
example: examples/retrieval_and_memory/grounding_verifier.py
contributors: ["@PrajwalAmte"]
last_updated: "2026-11"
description: After generation, check every factual sentence against the sources that were in the prompt, and cite, flag or remove what isn't supported.
sidebar:
  order: 5
---

## What It Is

A post-generation check for RAG answers. The answer is split into claims, and each claim is checked against the passages the model was given. Supported claims get a citation. Unsupported claims are flagged, removed, or sent back for one rewrite, depending on how much an error costs you.

It's the after-the-fact counterpart of the [Retrieval Quality Gate](retrieval-quality-gate.md). The gate keeps irrelevant context out of the prompt. The verifier catches the model saying things the context doesn't support.

## The Problem It Solves

Good retrieval doesn't guarantee a grounded answer. With the right pricing page in context, a model will still sometimes:

- Get a number wrong ("$59" when the page says "$49"). This is the most damaging case, because the sentence reads exactly like a correct one.
- Add a plausible detail from its training data ("includes a dedicated account manager").
- Cite source 2 for something that is only in source 1.

Users can't tell which sentences came from the sources and which didn't. In legal, medical, financial or policy answers, one invented sentence ruins an otherwise correct answer.

## How It Works

<pre class="mermaid">
flowchart TD
    R["Model answer"] --> X["Split into claims<br/>(skip questions, advice, hedges)"]
    X --> C["For each claim: best supporting passage<br/>(numbers must match exactly)"]
    C --> G{"Support ≥ threshold?"}
    G -->|"yes"| Y["Attach citation [n]"]
    G -->|"no"| P{"Policy"}
    P -->|"flag"| F["Mark [unverified]"]
    P -->|"suppress"| S["Remove sentence"]
    P -->|"regenerate"| W["One rewrite → re-verify → suppress leftovers"]
</pre>

1. **Extract claims.** Split the answer into sentences and drop the ones that aren't factual claims: questions, advice ("you can…"), pleasantries.
2. **Find support.** Score each claim against each passage. The example uses word overlap so it runs offline. In production, use an NLI model or a cross-encoder, which can tell "supports" apart from "mentions the same words".
3. **Treat numbers strictly.** A claim with a number is only supported by a passage containing that exact number. This one rule catches a large share of the errors that hurt.
4. **Apply a policy.** Flagging is cheap and honest. Suppression gives cleaner answers but can leave gaps. Regeneration gets one attempt, and anything still unsupported after that is suppressed. Never loop.
5. **Log the verdicts.** The rate of unsupported claims per feature is one of the most useful RAG quality metrics you can track.

## When to Use It

- Errors are costly: legal, medical, finance, compliance, or anything a customer might screenshot.
- Citations are a product feature, and they need to be right.
- You've seen answers that are mostly right with one invented detail.

## When NOT to Use It

- **The task is conversational or creative.** There's nothing to verify.
- **The answer is supposed to use general knowledge.** Grounding to retrieved context would wrongly flag every correct sentence the model knew on its own.
- **Your latency budget is already spent.** NLI over claims × passages adds real time. Verify only high-stakes answers, or run the check asynchronously and correct the answer afterwards.

## Trade-offs

- **Synthesis looks unsupported.** A correct inference drawn from two passages ("A is true and B is true, so C") has no single passage that states it. Single-passage verifiers will flag it. NLI over pairs of passages helps, at more cost.
- **Claim extraction is imperfect.** Over-extract and you spend money verifying opinions. Under-extract and you miss the one sentence that mattered.
- **Suppression changes meaning.** Removing a sentence can make the rest misleading ("Plan A includes X." with the "but only on annual billing" sentence removed). Prefer flagging when you aren't sure.

## Failure Modes

**Threshold set to pass everything.** With cosine similarity at a loose threshold, every claim finds a passage that's "similar enough", and the verifier becomes a decoration. Calibrate on labelled (claim, passage, supported?) examples from your own domain. Include near misses with wrong numbers and swapped entities.

**Regeneration loop.** The context doesn't contain the fact, and the model really wants to state it, so each rewrite brings it back. Allow one rewrite, then suppress, and tell the rewrite prompt which claims to drop.

**Right claim, stale source.** The claim matches the source perfectly, and the source is from last year. Grounding can't detect this. Pair the verifier with a [Retrieval Freshness Watermark](retrieval-freshness-watermark.md).

## Implementation Example

Claim extraction, a pluggable support scorer, strict number matching, and the three policies, with regeneration capped at one rewrite. The tests include the case that matters most: right words, wrong number.

```bash
cd examples && pytest retrieval_and_memory/test_grounding_verifier.py
```

<!-- example: examples/retrieval_and_memory/grounding_verifier.py -->
```python
"""Grounding Verifier.

After generation, check every factual sentence against the passages that were
actually in the prompt. Unsupported sentences are flagged, removed, or sent
back for one rewrite. Numbers get special treatment: a claim containing a
number is only grounded if a supporting passage contains that same number.

The default `support` scorer is lexical so this runs offline. In production,
swap in an NLI or cross-encoder model with the same signature.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

STOPWORDS = set("a an the is are was were be been of to in on for and or with by at as it this that from".split())
NUMBER = re.compile(r"\d+(?:[.,]\d+)*%?")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
NOT_A_CLAIM = re.compile(r"^(i think|you (can|should|might)|let me|please|feel free|hope this)\b|\?$", re.I)


def content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS}


def lexical_support(claim: str, passage: str) -> float:
    words = content_words(claim)
    if not words:
        return 1.0
    return len(words & content_words(passage)) / len(words)


@dataclass
class Verdict:
    claim: str
    grounded: bool
    source: int | None  # index of the supporting passage
    score: float


@dataclass
class VerifiedAnswer:
    text: str
    verdicts: list[Verdict] = field(default_factory=list)

    @property
    def ungrounded(self) -> list[str]:
        return [v.claim for v in self.verdicts if not v.grounded]


def extract_claims(response: str) -> list[str]:
    sentences = [s.strip() for s in SENTENCE.split(response) if s.strip()]
    return [s for s in sentences if not NOT_A_CLAIM.search(s)]


def check(
    claim: str, passages: list[str], support: Callable[[str, str], float], threshold: float
) -> Verdict:
    numbers = set(NUMBER.findall(claim))
    best, best_score = None, 0.0
    for i, passage in enumerate(passages):
        if numbers and not numbers <= set(NUMBER.findall(passage)):
            continue  # a passage that doesn't contain the number can't support it
        score = support(claim, passage)
        if score > best_score:
            best, best_score = i, score
    return Verdict(claim, best_score >= threshold, best, best_score)


def verify(
    response: str,
    passages: list[str],
    policy: str = "flag",  # "flag" | "suppress" | "regenerate"
    llm: Callable[[str], str] | None = None,
    support: Callable[[str, str], float] = lexical_support,
    threshold: float = 0.6,
) -> VerifiedAnswer:
    verdicts = [check(c, passages, support, threshold) for c in extract_claims(response)]
    bad = [v.claim for v in verdicts if not v.grounded]

    if bad and policy == "regenerate" and llm is not None:
        rewrite = llm(
            "Rewrite the answer using only facts stated in the sources. Remove these unsupported claims:\n"
            + "\n".join(f"- {c}" for c in bad)
            + "\n\nSources:\n" + "\n".join(passages) + f"\n\nAnswer:\n{response}"
        )
        # One rewrite only. If it still isn't grounded, fall back to suppression
        # rather than looping on a model that keeps reaching for the same claim.
        return verify(rewrite, passages, policy="suppress", support=support, threshold=threshold)

    text = response
    for v in verdicts:
        if v.grounded:
            text = text.replace(v.claim, f"{v.claim} [{v.source + 1}]", 1)
        elif policy == "suppress":
            text = text.replace(v.claim, "", 1)
        else:
            text = text.replace(v.claim, f"{v.claim} [unverified]", 1)
    return VerifiedAnswer(" ".join(text.split()), verdicts)
```
<!-- /example -->

## Tool Landscape

| Tool | Notes |
|---|---|
| Ragas (faithfulness), TruLens (groundedness) | Offline evaluation of the same property; good for calibrating thresholds |
| Vectara HHEM | Open model that scores whether a summary is consistent with its source |
| NLI cross-encoders (sentence-transformers) | Build-your-own entailment scoring |
| Provider citation features | Anthropic Citations, Google Vertex grounding: the model cites spans and you verify them |

## Related Patterns

- [Retrieval Quality Gate](retrieval-quality-gate.md) works before generation. This pattern works after. Use both.
- [LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md) is the general form. A grounding verifier is a narrow, cheaper, more checkable judge.
- [Hybrid Search](hybrid-search.md): better retrieval means fewer claims with no possible support.
- [Retrieval Freshness Watermark](retrieval-freshness-watermark.md) catches the claims that are grounded but stale.

## Further Reading

- [FActScore: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation](https://arxiv.org/abs/2305.14251), Min et al., 2023
- [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217), Es et al., 2023
- [Vectara Hallucination Evaluation Model](https://huggingface.co/vectara/hallucination_evaluation_model)
