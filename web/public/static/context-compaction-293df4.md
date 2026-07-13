---
title: Context Compaction
pillar: cost-and-efficiency
status: validated-in-production
tags: [context-window, compression, memory-management, token-optimization, summarization]
related:
  - Token Budget Pattern
  - Cascading Context Assembly
  - Multi-Agent Orchestration
contributors: ["@pattern-architect"]
last_updated: "2026-07"
description: Dynamically compress conversation history and intermediate state into structured summaries when context windows approach capacity, preserving critical information while freeing tokens for new content.
sidebar:
  order: 4
---

## What It Is

Context Compaction is a runtime technique that monitors context window utilization and triggers compression of accumulated history into condensed summaries when token counts approach defined thresholds. Instead of truncating old messages or restarting conversations, the system generates a structured summary of prior context and replaces verbose history with this compact representation, preserving decision-critical information while freeing tokens for continued operation.

## The Problem It Solves

Long-running conversations and multi-turn agent workflows accumulate context that eventually exceeds model limits. Without compaction, you face:

- **Hard cutoffs and lost state** — Naive truncation drops the oldest messages first, which often contain the original task description, user preferences, or plan state that remains relevant
- **Restart friction** — Starting a new conversation when limits are reached loses all accumulated context, forcing users to re-explain their goals and agents to re-derive insights
- **Escalating costs** — Passing full uncompressed history on every turn means token costs grow quadratically with conversation length even when most content is no longer decision-relevant
- **Context window waste** — Verbose tool outputs, repeated confirmations, and intermediate reasoning steps consume tokens without contributing to future decisions

## How It Works

1. **Threshold monitoring** — The system tracks accumulated token count or message count across the conversation. When a threshold is crossed (e.g., 80% of context window capacity, or >10 non-user messages), compaction triggers.

2. **Critical content identification** — The system identifies content that must survive compaction: the original user goal, explicit user constraints or preferences, key decisions made, and open loops requiring follow-up.

3. **Compression via summarization** — A model (often the same model in a separate call, or a smaller specialized model) generates a structured summary of the history, focusing on state and decisions rather than verbatim content.

4. **History replacement** — The verbose message history is replaced with the compact summary. The summary becomes a new system message or a special "memory" message type that persists across turns.

5. **Continuation with freed capacity** — The conversation continues with the compacted history, now fitting comfortably within the context window. New messages are appended as before.

6. **Iterative compaction** — If the conversation continues long enough, compaction can trigger multiple times, each time re-compressing the prior summary plus recent messages.

```mermaid
flowchart TD
    START([Conversation Begins]) --> MSGS[Accumulate Messages\nUser + Assistant + Tools]
    MSGS --> CHECK{Token count\n> threshold?}
    
    CHECK -- No --> CONTINUE[Continue Conversation]
    CONTINUE --> MSGS
    
    CHECK -- Yes --> EXTRACT[Extract Critical Info:\nGoals, Decisions, State]
    EXTRACT --> COMPRESS[Generate Structured\nSummary via LLM]
    COMPRESS --> REPLACE[Replace Verbose History\nwith Summary]
    REPLACE --> FREE[Freed Token Capacity]
    FREE --> CONTINUE
    
    CONTINUE --> END{Conversation\nComplete?}
    END -- No --> MSGS
    END -- Yes --> FINAL([End])
```

## When to Use It

- Conversations or agent tasks that span more than 10-15 turns with verbose tool outputs or long assistant responses
- Multi-agent orchestration where the lead agent accumulates results from multiple workers and risks context overflow mid-task
- Long-horizon tasks (e.g., multi-day coding sessions, extended research) where restarting conversations would lose critical accumulated state
- Applications with a fixed context window budget where you cannot afford to upgrade to larger-context models
- Systems where token costs are a primary constraint and you need to minimize redundant context passed on every turn

## When NOT to Use It

- **Short, single-turn interactions** — If conversations rarely exceed 3-5 turns, compaction overhead exceeds any benefit
- **Lossless context is required** — Compaction is inherently lossy; if every word of prior history must be preserved exactly (e.g., legal review, audit trails), use external storage and retrieval instead
- **Context window is abundant** — If you operate with 200k+ token models and typical conversations use <10k tokens, compaction complexity is unnecessary
- **Real-time latency is critical** — Compaction adds a synchronous summarization call that blocks the conversation; if every millisecond matters, this may be unacceptable
- **You lack quality summarization models** — Compaction depends on accurate summarization; if your model produces poor summaries, you'll lose critical state

## Trade-offs

1. **Token cost savings vs. summarization overhead** — Compaction reduces cumulative tokens passed across turns (often 40-60% savings on long conversations), but each compaction event requires a separate summarization call. You trade one expensive call now for savings on all future turns. This is profitable when conversations continue for many turns post-compaction, but wasteful if conversations end immediately after compaction.

2. **Latency penalty vs. long-term viability** — Triggering compaction mid-conversation adds a synchronous delay (typically 1-3 seconds for a summarization call). The benefit is that the conversation remains viable indefinitely rather than hitting a hard stop when context fills. Users perceive this as a "thinking" pause rather than a failure, making it acceptable in most non-realtime applications.

3. **Lossiness vs. practicality** — Summaries inevitably lose nuance: exact phrasing, tone, some edge-case details. The benefit is that conversations can continue where they otherwise could not. The key is preserving *decision-relevant* information (user goals, constraints, key facts) rather than *all* information. Compaction is a pragmatic trade-off: some loss for continued operation.

4. **Complexity vs. user experience** — Implementing compaction adds complexity: threshold tuning, summary prompt engineering, handling compaction failures. The benefit is invisible to users when it works — they simply experience conversations that never "run out of room." This behind-the-scenes complexity delivers a seamless UX that naive truncation cannot provide.

## Failure Modes

| Trigger | Symptom | Mitigation |
|---------|---------|-----------|
| Premature compaction triggers | Compaction fires after only 3-4 turns, adding latency for minimal benefit | Raise threshold to 70-80% of context window, not 50%; use token count not message count if messages vary widely in size |
| Critical state loss in summary | User's original goal, key constraints, or open tasks omitted from compressed summary | Explicitly prompt summarizer to preserve: original request, user preferences, decisions made, and pending actions; validate summary against a checklist |
| Compaction call fails | Summarization model times out or errors; conversation stuck with no viable history | Implement fallback: truncate oldest non-critical messages and continue; log for manual review |
| Summary quality degrades iteratively | Multiple compaction rounds produce progressively vaguer summaries (lossy compression compounds) | Limit compaction depth (e.g., max 3 rounds) or retain full history in external storage and re-summarize from source on Nth compaction |
| User confusion at "memory gaps" | User references something said 20 turns ago that was dropped in compaction; assistant appears to forget | Surface compaction events to users ("I've condensed our conversation to focus on key points"); allow users to request full history retrieval |

## Implementation Example

```python
from anthropic import Anthropic
from typing import List, Dict

class ConversationWithCompaction:
    def __init__(self, client: Anthropic, model: str = "claude-sonnet-4", max_tokens: int = 100000):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.compaction_threshold = int(max_tokens * 0.75)  # Trigger at 75% capacity
        self.messages: List[Dict] = []
        self.is_compacted = False
        
    def estimate_tokens(self, messages: List[Dict]) -> int:
        """Rough token estimator (1 token ≈ 4 chars for English text)."""
        return sum(len(msg.get("content", "")) for msg in messages) // 4
    
    def should_compact(self) -> bool:
        """Check if compaction threshold is exceeded."""
        return self.estimate_tokens(self.messages) > self.compaction_threshold
    
    def compact_history(self) -> None:
        """Generate summary and replace verbose history."""
        print("⚙️ Compacting conversation history...")
        
        # Identify critical content to preserve
        original_request = next((m["content"] for m in self.messages if m["role"] == "user"), "")
        
        # Build compaction prompt
        history_text = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in self.messages])
        compaction_prompt = f"""Summarize this conversation into a structured memory that preserves:
1. The user's original goal and any constraints they specified
2. Key decisions made or conclusions reached
3. Current task state and any pending actions
4. Important context that will be needed to continue the conversation

Be concise but preserve decision-critical information.

CONVERSATION HISTORY:
{history_text}

STRUCTURED SUMMARY:"""
        
        # Generate summary
        response = self.client.messages.create(
            model=self.model,
            max_tokens=2000,
            messages=[{"role": "user", "content": compaction_prompt}]
        )
        
        summary = response.content[0].text
        
        # Replace history with compacted summary
        self.messages = [
            {"role": "user", "content": f"[CONVERSATION MEMORY]\n{summary}\n[END MEMORY]"}
        ]
        self.is_compacted = True
        print(f"✅ History compacted: {len(history_text)} chars → {len(summary)} chars")
    
    def send_message(self, user_message: str) -> str:
        """Send a message, triggering compaction if needed."""
        # Add user message
        self.messages.append({"role": "user", "content": user_message})
        
        # Check if compaction needed before model call
        if self.should_compact() and not self.is_compacted:
            self.compact_history()
        
        # Get model response
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            messages=self.messages
        )
        
        assistant_message = response.content[0].text
        self.messages.append({"role": "assistant", "content": assistant_message})
        
        # Reset compaction flag (can compact again later if needed)
        if self.is_compacted and len(self.messages) > 5:
            self.is_compacted = False
        
        return assistant_message

# Usage
client = Anthropic(api_key="your-api-key")
conversation = ConversationWithCompaction(client, max_tokens=50000)

# Simulate a long conversation
for i in range(20):
    response = conversation.send_message(f"Tell me about topic {i} in detail.")
    print(f"Turn {i+1}: {response[:100]}...")
    # Compaction will automatically trigger when threshold is reached
```

## Tool Landscape

**Agent frameworks with built-in compaction:**
- OpenAI Agents SDK — `OpenAIResponsesCompactionSession` with configurable thresholds
- LangChain — `ConversationSummaryMemory` and `ConversationSummaryBufferMemory`
- Semantic Kernel (Microsoft) — memory consolidation plugins
- Haystack — conversation summarization nodes in pipelines

**Specialized memory/compression libraries:**
- MemGPT — hierarchical memory with automatic tiering and compaction
- GPTCache — semantic caching with built-in summarization for long contexts
- LlamaIndex — document summarization and memory compaction utilities

**Observability for compaction monitoring:**
- LangSmith — track token usage before/after compaction events
- Weights & Biases Weave — visualize conversation token growth and compaction triggers
- Helicone — token usage dashboards with compaction event annotations

## Further Reading

1. [MemGPT: Towards LLMs as Operating Systems — Packer et al., 2023](https://arxiv.org/abs/2310.08560)
2. [OpenAI Agents SDK Sessions Documentation — Memory Management, 2025](https://platform.openai.com/docs/agents/sessions)
3. [LangChain Memory Types — Conversation Summarization, 2024](https://python.langchain.com/docs/modules/memory/types/)
4. [Efficient Long-Context Scaling of Foundation Models — Chen et al., 2023](https://arxiv.org/abs/2309.00071)
