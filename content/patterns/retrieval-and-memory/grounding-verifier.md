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
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Verify that each factual claim in an LLM response is traceable to a retrieved source, and flag or suppress ungrounded assertions before serving.
sidebar:
  order: 5
---

## What It Is

A Grounding Verifier sits between the LLM response and the user, checking whether factual claims in the response are supported by the retrieved context that was injected into the prompt. For each verifiable claim extracted from the response, the verifier checks for a supporting passage in the source documents. Claims with no supporting source are flagged as ungrounded, triggering either in-response citation gaps, response regeneration, or explicit uncertainty markers. This is a post-generation complement to pre-generation filters like Retrieval Quality Gate.

## The Problem It Solves

RAG systems are designed to ground model responses in retrieved documents, but in practice they hallucinate even when the context is relevant:

- **Context-ignoring hallucination**: The model uses its parametric knowledge instead of retrieved context, producing answers that contradict the sources.
- **Partial grounding**: The model correctly cites some facts from context but invents other details in the same response.
- **Confident confabulation**: The model synthesizes a plausible-sounding answer that blends retrieved facts with fabricated details in ways that are impossible to distinguish without checking sources.
- **Attribution drift**: The model attributes a claim to "Source A" when Source A does not contain that claim.

Retrieval Quality Gate prevents irrelevant context from entering the prompt. Grounding Verifier catches what slips through—claims that appear grounded but are not. These are different failure modes. A relevant, high-quality chunk can still cause hallucination if the model misreads or extrapolates from it.

## How It Works

<pre class="mermaid">
flowchart TD
    A[LLM generates response] --> B[Claim extractor]
    B --> C[Claim 1: X is true]
    B --> D[Claim 2: Y costs Z]
    B --> E[Claim 3: A was released in year N]
    C --> F[Check claim against retrieved sources]
    D --> F
    E --> F
    F --> G{Supported by source?}
    G -->|Yes: citation found| H[Mark as grounded]
    G -->|No source supports| I[Mark as ungrounded]
    H --> J[Assemble verified response]
    I --> K{Policy: regenerate, flag, or suppress?}
    K -->|Regenerate| L[Request revised response without ungrounded claim]
    K -->|Flag| M[Append uncertainty marker to claim]
    K -->|Suppress| N[Remove claim from response]
    J --> O[Return verified response]
    L --> O
    M --> O
    N --> O
</pre>

1. **Claim extraction**: Parse the LLM response to extract verifiable factual claims—declarative statements about the world that could be true or false (not opinions, questions, or instructions). Use a small LLM or rule-based extractor.
2. **Source matching**: For each claim, check whether any passage in the retrieved context supports it:
   - Semantic similarity between claim and context passages (embedding cosine similarity)
   - Cross-encoder relevance scoring (claim, passage) to get a grounding score
   - Optional: NLI (Natural Language Inference) model to check if passage entails the claim
3. **Grounding decision**: Apply threshold. Claim is "grounded" if at least one source passage scores above threshold. Claim is "ungrounded" otherwise.
4. **Policy application**: For ungrounded claims, apply configured policy:
   - **Regenerate**: Remove ungrounded claims from context and ask model to revise
   - **Flag**: Insert inline markers ("[citation needed]", confidence score)
   - **Suppress**: Remove the claim from the final response
5. **Citation attachment**: For grounded claims, attach source references that can be surfaced in the UI.

## When to Use It

- High-stakes domains where hallucinations cause real harm (legal, medical, financial, compliance)
- Customer-facing applications where citing sources is a product requirement
- You observe that your RAG system produces partially-hallucinated responses despite having relevant context
- Regulatory or audit requirements mandate traceable AI-generated claims
- You want to provide users with source citations alongside answers

## When NOT to Use It

- Low-stakes, conversational, or creative tasks where strict grounding is not required
- Responses that are primarily opinions, recommendations, or procedural instructions (not verifiable fact claims)
- High-throughput systems where per-claim verification adds unacceptable latency (adds 300-800ms)
- Contexts where the model is expected to use parametric knowledge and no retrieved context exists
- When all factual claims in the domain are simple enough to be verified by retrieval alone

## Trade-offs

1. **Latency overhead** — Extracting claims, embedding them, and cross-encoding against source passages adds 300-800ms per response. For claim-heavy responses with 10+ assertions, this can exceed one second. Use claim sampling (verify a random subset) to reduce latency at the cost of coverage.

2. **Extractor accuracy** — Not all statements in a response are verifiable fact claims. If the claim extractor over-extracts (treats opinions as facts), you waste verification compute. If it under-extracts (misses important claims), you miss hallucinations.

3. **False ungrounded on implicit support** — The model correctly paraphrases or synthesizes a claim from multiple sources, but no single source explicitly states it. Verifier marks it as ungrounded despite being correct. Over-suppression damages response quality.

4. **Regeneration cost and loops** — If policy is to regenerate on ungrounded claims, each regeneration costs another full LLM call. If the model repeatedly introduces the same ungrounded claim, you enter a regeneration loop. Cap regeneration attempts at one or two.

## Failure Modes

### Claim Extraction Miss on Numeric Facts
**Trigger**: Claim extractor misses numeric or statistical claims embedded in prose ("The system achieves 98% uptime"). These are high-risk but structurally different from named-entity claims.
**Symptom**: Numeric hallucinations pass through verifier undetected. Users receive confident wrong statistics.
**Mitigation**: Add pattern-based extraction for numeric claims: percentages, dates, currency values, measurements. Treat these as mandatory verification targets regardless of extractor output.

### Semantic Similarity Threshold Miscalibration
**Trigger**: Threshold set too low (e.g., 0.6). Vaguely related passages score above threshold for unrelated claims.
**Symptom**: Verifier passes false information. Trust in the grounding check erodes.
**Mitigation**: Calibrate threshold on a labeled dataset of (claim, passage, grounded/ungrounded) triples from your domain. Use a cross-encoder or NLI model instead of cosine similarity for higher precision.

### Implicit Knowledge Suppression
**Trigger**: Model synthesizes a correct inference from two source passages ("If A is true and B is true, then C"), but no single passage asserts C directly. Verifier flags C as ungrounded.
**Symptom**: Response quality degrades as legitimate inferences are suppressed. Users receive incomplete or hedge-heavy answers.
**Mitigation**: Use NLI-based verification (does any combination of passages entail this claim?) rather than single-passage matching. Only suppress when confidence of ungroundedness is very high.

### Regeneration Loop
**Trigger**: Claim is ungrounded because the context does not contain the required information. Model regenerates but halluccinates the same claim again (parametric knowledge leakage).
**Symptom**: Multiple regeneration rounds, high latency, same ungrounded claim reappears.
**Mitigation**: On first regeneration failure, switch to suppression or flagging policy. Add explicit instruction to regeneration prompt: "Only include claims you can directly cite from the provided sources."

## Implementation Example

```python
from dataclasses import dataclass
from typing import Literal
from sentence_transformers import CrossEncoder
import numpy as np

@dataclass
class Claim:
    text: str
    grounded: bool = False
    source_index: int = -1
    confidence: float = 0.0

@dataclass
class VerificationResult:
    original_response: str
    claims: list[Claim]
    verified_response: str
    grounding_rate: float

class GroundingVerifier:
    """
    Verifies factual claims in LLM responses against retrieved source passages.
    """

    def __init__(
        self,
        cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
        grounding_threshold: float = 0.6,
        policy: Literal["flag", "suppress", "regenerate"] = "flag"
    ):
        self.cross_encoder = CrossEncoder(cross_encoder_model)
        self.threshold = grounding_threshold
        self.policy = policy

    async def extract_claims(self, response: str, llm_call) -> list[str]:
        """Extract verifiable factual claims from response using a small LLM"""
        prompt = f"""Extract every verifiable factual claim from this text.
Return one claim per line. Only include declarative statements about facts,
not opinions, questions, or procedural instructions.

Text: {response}

Claims (one per line):"""
        result = await llm_call(model="gpt-4o-mini", prompt=prompt)
        return [c.strip() for c in result.strip().split("\n") if c.strip()]

    def check_claim_grounding(
        self, claim: str, source_passages: list[str]
    ) -> tuple[bool, int, float]:
        """
        Check if claim is supported by any source passage.
        Returns (grounded, best_source_index, confidence_score).
        """
        if not source_passages:
            return False, -1, 0.0

        pairs = [(claim, passage) for passage in source_passages]
        scores = self.cross_encoder.predict(pairs)

        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])
        # Approximate normalization of cross-encoder score to [0, 1]
        normalized = max(0.0, min(1.0, (best_score + 10) / 20))
        grounded = normalized >= self.threshold
        return grounded, best_idx if grounded else -1, normalized

    def apply_policy(self, response: str, claims: list[Claim]) -> str:
        """Apply configured policy to ungrounded claims"""
        ungrounded = [c for c in claims if not c.grounded]
        if not ungrounded:
            return response

        if self.policy == "flag":
            modified = response
            for claim in ungrounded:
                modified = modified.replace(
                    claim.text,
                    f"{claim.text} [unverified — not found in sources]"
                )
            return modified

        elif self.policy == "suppress":
            modified = response
            for claim in ungrounded:
                modified = modified.replace(claim.text, "")
            return modified.strip()

        elif self.policy == "regenerate":
            return "__REGENERATE__"

        return response

    async def verify(
        self, response: str, source_passages: list[str], llm_call
    ) -> VerificationResult:
        """Full pipeline: extract claims, check grounding, apply policy."""
        claim_texts = await self.extract_claims(response, llm_call)

        claims = []
        for claim_text in claim_texts:
            grounded, source_idx, confidence = self.check_claim_grounding(
                claim_text, source_passages
            )
            claims.append(Claim(
                text=claim_text,
                grounded=grounded,
                source_index=source_idx,
                confidence=confidence
            ))

        verified_response = self.apply_policy(response, claims)
        grounding_rate = (
            sum(1 for c in claims if c.grounded) / len(claims) if claims else 1.0
        )

        return VerificationResult(
            original_response=response,
            claims=claims,
            verified_response=verified_response,
            grounding_rate=grounding_rate
        )


# Usage in RAG pipeline
async def grounded_rag(query: str, vector_db, llm_call) -> str:
    docs = vector_db.similarity_search(query, k=5)
    passages = [doc.page_content for doc in docs]
    context = "\n\n".join(passages)

    prompt = f"Answer the question based on the following context:\n\n{context}\n\nQuestion: {query}"
    response = await llm_call(model="gpt-4o", prompt=prompt)

    verifier = GroundingVerifier(grounding_threshold=0.6, policy="flag")
    result = await verifier.verify(response, passages, llm_call)

    if result.verified_response == "__REGENERATE__":
        strict_prompt = (
            f"{prompt}\n\n"
            "Only include facts explicitly stated in the provided context. "
            "Do not add any information not found in the sources."
        )
        response = await llm_call(model="gpt-4o", prompt=strict_prompt)
        result = await verifier.verify(response, passages, llm_call)

    print(f"Grounding rate: {result.grounding_rate:.0%} ({len(result.claims)} claims)")
    return result.verified_response
```

## Tool Landscape

| Tool | Type | Notes |
|------|------|-------|
| Ragas | Open-source | Faithfulness metric checks if response claims are grounded in retrieved context |
| TruLens | Open-source | Groundedness evaluation as part of RAG triad (context relevance, groundedness, answer relevance) |
| LlamaIndex | RAG framework | FaithfulnessEvaluator checks claim support in source nodes |
| Vertex AI Grounding | Managed | Google built-in grounding check for Gemini responses; integrates with Search |
| Vectara | Managed RAG | Built-in hallucination detection score (Hughes Hallucination Evaluation Model) |
| sentence-transformers | Open-source | Cross-encoder models for (claim, passage) entailment scoring |

## Related Patterns

- **[Retrieval Quality Gate](retrieval-quality-gate.md)** — Gate filters irrelevant chunks before generation; Grounding Verifier catches hallucinations after generation. Use both for defense-in-depth.
- **[LLM-as-Judge](../observability-and-evaluation/llm-as-judge.md)** — Grounding Verifier is a specialized form of LLM-as-Judge focused on claim-source entailment rather than general quality.
- **[Hybrid Search](hybrid-search.md)** — Better retrieval produces more precise sources, making grounding verification more reliable and reducing false ungrounded flags.
- **[Retrieval Freshness Watermark](retrieval-freshness-watermark.md)** — Even grounded claims can be wrong if the source is outdated. Combine freshness watermarking with grounding verification to catch both ungrounded and stale claims.

## Further Reading

- [RAGAS: Automated Evaluation of Retrieval Augmented Generation](https://arxiv.org/abs/2309.15217) — Defines the faithfulness metric that underpins grounding verification
- [Measuring Faithfulness in Chain-of-Thought Reasoning](https://arxiv.org/abs/2307.13702) — Research on faithfulness as a property of LLM reasoning chains
- [FActScoring: Fine-grained Atomic Evaluation of Factual Precision](https://arxiv.org/abs/2305.14251) — Academic framework for claim-level factual verification
- [Vectara Hughes Hallucination Evaluation Model](https://huggingface.co/vectara/hallucination_evaluation_model) — Open-source model trained specifically for RAG hallucination detection
