---
title: Glossary
description: Key terms used throughout AI Engineering Patterns.
---

## A

**Agent** — An AI system that can autonomously plan and execute multi-step tasks using tools and external APIs. Distinguished from simple LLM calls by the ability to take actions beyond text generation.

## B

**Batch Inference** — Processing multiple inference requests together rather than individually. Trades latency for throughput and cost efficiency.

**BM25** — A probabilistic keyword-based ranking function used in sparse retrieval. Relies on term frequency and document length normalization rather than learned embeddings.

## C

**Canary Deployment** — Releasing a new model or prompt version to a small subset of traffic before full rollout. Limits blast radius of quality regressions.

**Cascading Context Assembly** — A pattern that dynamically assembles context from multiple tiers (cache, metadata, vector store, live retrieval) in order of increasing cost and latency. Stops as soon as a confidence threshold is met, avoiding unnecessary expensive retrievals.

**Chain-of-Thought (CoT)** — Prompting strategy that asks the model to show intermediate reasoning steps. Improves accuracy on complex tasks at the cost of additional output tokens.

**Chunking** — Splitting documents into smaller segments for embedding and retrieval. Chunk size and strategy directly affect retrieval quality.

**Circuit Breaker** — A pattern that monitors failure rates and temporarily stops sending requests to a degraded service. Prevents cascade failures and allows recovery time.

**Context Window** — The maximum number of tokens a model can process in a single request, including both input and output tokens.

## D

**Data Contract** — A formal agreement between data producers and consumers specifying schema, quality thresholds, and SLAs. Prevents upstream changes from silently breaking downstream systems.

**Dense Retrieval** — Using learned vector embeddings to find semantically similar documents. Captures meaning rather than exact keyword matches.

**Distribution Shift** — When the statistical properties of input data in production differ from what was expected during development or training.

## E

**Embedding** — A fixed-size vector representation of text (or other data) in a continuous vector space. Similar meanings map to nearby vectors.

**Embedding Drift** — Gradual or sudden changes in the distribution of embedding vectors over time, caused by new vocabulary, shifting user behaviour, or model updates. Detected by monitoring statistical properties of embedding populations.

**Eval Dataset** — A curated set of input-output pairs used to measure model or system quality. Distinct from training data.

## F

**Fallback Chain** — An ordered list of alternative providers or models to try when the primary option fails or degrades.

**Feature Store** — A centralized repository for storing, versioning, and serving ML features. Ensures consistency between training and serving.

**Fine-Tuning** — Continuing the training of a pre-trained model on domain-specific data to improve performance on targeted tasks.

## G

**Graceful Degradation** — Returning a reduced-quality but still useful response when the full system is unavailable, rather than returning an error.

**GraphRAG** — Retrieval-augmented generation that uses knowledge graphs instead of (or alongside) vector stores. Handles relational and multi-hop queries.

**Guardrails** — Input and output validation layers that enforce safety, quality, and compliance constraints on LLM interactions.

## H

**Hallucination** — When a model generates content that is factually incorrect, fabricated, or not grounded in the provided context.

**Human-in-the-Loop (HITL)** — A design pattern where certain automated decisions require human approval before execution. Used for high-risk or high-stakes actions.

**Hybrid Search** — Combining dense (vector) and sparse (keyword) retrieval methods and merging their results. Consistently outperforms either method alone.

## I

**Inference** — The process of running a trained model on new inputs to produce outputs. In production AI, this typically means making API calls to LLM providers.

**Inference-Time Compute** — Allocating additional computation (more reasoning steps, multiple samples) at inference time to improve quality on hard queries.

## L

**Lakehouse** — A data architecture combining data lake flexibility with data warehouse reliability. Provides ACID transactions, versioning, and schema enforcement.

**Lineage** — The complete tracking of data from raw source through transformations, training, and inference. Required for compliance and debugging.

**LLM Gateway** — A centralized proxy layer between applications and LLM providers that handles routing, authentication, rate limiting, logging, and failover.

## M

**Model Card** — Standardized documentation of a model's capabilities, limitations, intended uses, training data, and known failure modes.

**Model Router** — A system that routes inference requests to different models based on query complexity, cost targets, or latency requirements.

## O

**Observability** — The ability to understand the internal state of a system from its external outputs. For AI systems, this includes tracing, metrics, logging, and quality monitoring.

## P

**Pagefind** — A static site search library that indexes content at build time. Used by this site for full-text search without external services.

**PII (Personally Identifiable Information)** — Any data that could identify a specific individual. Must be detected and handled before entering prompts or logs.

**Policy-as-Code** — Encoding compliance rules as machine-checkable assertions that run automatically in CI/CD pipelines.

**Prompt Canary Deployment** — A governance pattern that routes a small percentage of live traffic to a new prompt version while the majority continues on the current version. Automated quality metrics decide whether to promote or roll back the candidate.

**Prompt Injection** — An attack where malicious instructions are embedded in user input to manipulate model behavior. The LLM equivalent of SQL injection.

**Prompt Regression** — When changes to prompts, system instructions, or models cause quality to degrade on previously passing test cases.

## R

**RAG (Retrieval-Augmented Generation)** — A pattern that retrieves relevant context from external sources and includes it in the prompt before generation. Grounds model outputs in actual data.

**Reranking** — A two-stage retrieval approach where a first-pass retriever returns candidates and a second-pass model scores and reorders them for relevance.

**Retrieval Freshness Watermark** — A metadata-driven pattern that stamps every retrieved chunk with a freshness timestamp and TTL, allowing the retrieval layer to filter or flag stale content before it enters the LLM context.

## S

**Semantic Caching** — Caching LLM responses indexed by the semantic meaning of queries rather than exact string matches. Serves similar (not just identical) queries from cache.

**Semantic Deduplication** — A data-quality pattern that detects and merges near-duplicate records using embedding similarity rather than exact-match keys. Prevents redundant context from inflating retrieval results and token costs.

**Shadow Mode** — Running a new model in parallel on live traffic without serving its outputs to users. Used to compare quality before switching.

**SLO (Service Level Objective)** — A target value for a service metric (latency, quality, cost) that defines acceptable performance. More specific than an SLA.

**Span** — A single unit of work within a trace. In AI systems, spans typically represent retrieval, prompt construction, inference, and postprocessing steps.

**Sparse Retrieval** — Keyword-based retrieval methods (like BM25) that match on exact terms rather than learned representations.

**Structured Output** — Constraining model output to match a predefined schema (JSON, XML) using tools like Pydantic or Zod. Eliminates parsing failures.

## T

**TTFT (Time to First Token)** — The latency between sending a request and receiving the first token of the response. Critical for perceived responsiveness in streaming applications.

**Token** — The fundamental unit of text that LLMs process. A token is roughly 3/4 of a word in English. Costs are typically measured per token.

**Token Budget** — A hard limit on the number of input and/or output tokens per request. Prevents unbounded costs from long contexts or verbose outputs.

**Tool Output Firewall** — A security pattern that validates, sanitizes, and constrains data returned by external tools before it re-enters the LLM context window. Prevents indirect prompt injection and data exfiltration through tool results.

**Train/Serve Skew** — Differences between the data or features used during model training and those available during serving. A common source of production quality issues.

## V

**Vector Store** — A database optimized for storing and querying high-dimensional vectors (embeddings). The storage layer for dense retrieval in RAG systems.
