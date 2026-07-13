---
title: Sliding Context Window with Memory Consolidation
pillar: retrieval-and-memory
status: emerging
tags: [memory, conversation, context-management, summarization, compression]
related:
  - Context Compaction
  - Cascading Context Assembly
  - Token Budget
contributors: ["@PrajwalAmte"]
last_updated: "2026-07"
description: Maintain long conversations by keeping recent turns verbatim and consolidating old turns into factual summaries to prevent context overflow.
sidebar:
  order: 4
---

## What It Is

Sliding Context Window with Memory Consolidation divides conversation history into zones: an immutable system prompt, a sliding window of recent turns kept verbatim, and a consolidated archive of old turns compressed into factual summaries. As new turns arrive, the oldest verbatim turns are moved to the archive and consolidated, preserving critical facts while maintaining recent conversational coherence. This asymmetric compression strategy prevents context overflow in long conversations without losing essential historical context.

## The Problem It Solves

In long multi-turn conversations (customer support, tutoring, therapy, sales), context windows fill up quickly. Common failure patterns:

- **Naive truncation**: Drop oldest turns when context is full. Critical earlier information (user preferences, constraints, decisions made) is lost. Model forgets what was already discussed.
- **Naive full summarization**: Compress entire history into a summary. Loses fine-grained recent context needed for coherent responses ("as I mentioned earlier..." references fail).
- **No compression**: Keep all turns verbatim until context overflows, then crash or silently truncate. Users experience sudden amnesia mid-conversation.

The challenge: recent turns need verbatim preservation for conversational coherence, while old turns need compression to save space. A single strategy for all history doesn't work—you need asymmetric treatment based on recency.

## How It Works

<pre class="mermaid">
flowchart TD
    A[New user turn arrives] --> B[Add to verbatim window]
    B --> C{Verbatim window size > threshold?}
    C -->|No| D[Continue conversation]
    C -->|Yes| E[Extract oldest N turns from verbatim]
    E --> F[Consolidate: extract facts, decisions, constraints]
    F --> G[Append summary to consolidated archive]
    G --> H[Remove consolidated turns from verbatim]
    H --> D
    D --> I[Assemble context for LLM]
    I --> J[Immutable prompt + Archive + Verbatim window]
    J --> K[Generate response]
</pre>

### Context Zones

1. **Immutable zone** (always present):
   - System prompt defining assistant behavior
   - User profile (name, preferences, verified facts)
   - Session metadata (language, timezone, special needs)

2. **Verbatim window** (last N turns, default N=10):
   - Recent conversation kept word-for-word
   - Maintains coherence, allows "as you said" references
   - Size: typically 8-12 turns or 2000-4000 tokens

3. **Consolidated archive** (compressed old turns):
   - Factual summaries of earlier conversation
   - Preserves: decisions made, constraints stated, facts learned
   - Drops: chitchat, redundancy, verbosity
   - Format: bullet-point facts or chronological summary

### Consolidation Process

When verbatim window exceeds threshold (e.g., 12 turns):
1. Extract oldest 5 turns from verbatim window
2. Send to consolidation LLM with prompt:
   ```
   Extract key facts, decisions, and constraints from this conversation fragment.
   Preserve information needed to maintain continuity (user preferences, agreed plans, important details).
   Drop small talk and redundant content.
   ```
3. Append resulting summary to consolidated archive
4. Remove the 5 turns from verbatim window
5. Continue conversation with new context structure

## When to Use It

- Conversations regularly exceeding 10-15 turns
- Multi-session interactions where history matters (customer support, tutoring, therapy)
- Context window is a hard constraint (e.g., 8k tokens, tight budget models)
- Earlier conversation contains facts critical to current turn (user preferences, past decisions)
- Conversational coherence matters ("as we discussed earlier" references must work)
- Users expect the assistant to "remember" information from early in the conversation

## When NOT to Use It

- Single-shot QA with no conversation history
- Conversations rarely exceed 5 turns (consolidation overhead not justified)
- Context window is large enough to hold entire conversation (32k+ tokens)
- Earlier context is irrelevant to current turn (transactional chatbots, FAQ bots)
- You're already using a different memory system (vector DB retrieval, external memory store)
- Latency budget cannot afford 1-3s consolidation overhead when threshold is hit

## Trade-offs

1. **Compression loss** — Summaries lose nuance, emotional tone, and exact phrasing. If user said "I'm allergic to peanuts" in turn 5, consolidation might summarize as "User has dietary restrictions" (too vague) or drop it entirely if deemed unimportant by the consolidation LLM.

2. **Consolidation latency** — When threshold is hit, conversation pauses 1-3 seconds for summarization. Visible to user as increased response time on specific turns. Can be mitigated with async consolidation but risks race conditions.

3. **Cost of consolidation** — Each consolidation pass is an LLM call. With 5 turns consolidated every 10 new turns, you add ~0.5 LLM calls per user turn overhead. At scale, this is significant.

4. **Coherence breaks** — Model may reference exact phrasing from earlier turn, but that turn is now in compressed archive with different wording. Causes "I don't recall saying that" moments.

## Failure Modes

### Premature Consolidation Loss
**Trigger**: User makes important statement in turn 8. Conversation continues, and by turn 20, turn 8 has been consolidated. Consolidation LLM deems it unimportant and drops it.  
**Symptom**: User references earlier statement in turn 25, but model has no memory of it. User frustrated: "I already told you this!"  
**Mitigation**: Use importance-weighted consolidation: extract entities, user preferences, constraints first before summarizing. Tag critical facts as "pinned" to prevent compression. Allow user to explicitly flag important information: "Remember this."

### Consolidation Latency Spike
**Trigger**: Consolidation happens synchronously on turn 13, adding 2.5s to response time. User perceives the conversation as "hanging."  
**Symptom**: Uneven response times. Users report "sometimes it's fast, sometimes it freezes."  
**Mitigation**: Run consolidation asynchronously after responding to user. Risk: next turn may arrive before consolidation completes, leading to race condition (consolidating already-moved turns). Use optimistic locking or skip consolidation if next turn arrives within consolidation window.

### Over-Compression of Recent Context
**Trigger**: Window threshold set too low (e.g., 5 turns). Model consolidates turn 3 while user still expects verbatim recall.  
**Symptom**: Conversational incoherence. Model cannot reference recent exact phrasing, uses paraphrased archive instead.  
**Mitigation**: Calibrate window size to conversational context: 8-12 turns for general chat, 15-20 for technical support where exact commands matter. Monitor user feedback on "model forgot what I said."

### Archive Bloat
**Trigger**: Long conversation (100+ turns) generates large consolidated archive. Archive itself approaches context limit.  
**Symptom**: Context overflow despite consolidation. Archive consumes 6k tokens, leaving little room for verbatim window.  
**Mitigation**: Re-consolidate the archive periodically: summarize the summary after every 50 turns. Use hierarchical summarization (turn-level → session-level → conversation-level). Store full history externally, retrieve only relevant archive segments via semantic search.

## Implementation Example

```python
from dataclasses import dataclass, field
from typing import List, Optional
import asyncio

@dataclass
class Message:
    role: str  # "user" or "assistant"
    content: str
    turn_id: int
    timestamp: float

@dataclass
class ConversationMemory:
    """
    Manages sliding context window with memory consolidation.
    """
    verbatim_window_size: int = 10
    consolidation_batch_size: int = 5
    max_archive_tokens: int = 4000
    
    # State
    verbatim: List[Message] = field(default_factory=list)
    consolidated_archive: str = ""
    turn_counter: int = 0
    
    # Consolidation callback
    consolidation_fn: Optional[callable] = None

    async def add_turn(self, role: str, content: str) -> None:
        """
        Add a new turn to the conversation. Consolidates if window overflows.
        """
        msg = Message(
            role=role,
            content=content,
            turn_id=self.turn_counter,
            timestamp=asyncio.get_event_loop().time()
        )
        self.turn_counter += 1
        self.verbatim.append(msg)
        
        # Check if verbatim window overflow
        if len(self.verbatim) > self.verbatim_window_size:
            await self._consolidate_oldest_turns()
    
    async def _consolidate_oldest_turns(self) -> None:
        """
        Move oldest turns from verbatim to consolidated archive.
        """
        # Extract oldest batch
        to_consolidate = self.verbatim[:self.consolidation_batch_size]
        self.verbatim = self.verbatim[self.consolidation_batch_size:]
        
        # Format for consolidation
        turns_text = "\n".join([
            f"{msg.role.upper()}: {msg.content}"
            for msg in to_consolidate
        ])
        
        # Consolidation prompt
        consolidation_prompt = f"""Extract key facts, decisions, constraints, and user preferences from this conversation fragment.

Preserve information critical to maintaining context in future turns:
- User preferences and requirements
- Decisions made or plans agreed upon
- Important facts disclosed by either party
- Constraints or limitations mentioned

Omit:
- Small talk and greetings
- Redundant information already captured
- Verbose explanations (keep only the fact)

Conversation fragment:
{turns_text}

Factual summary (bullet points):"""
        
        # Call consolidation function (LLM or custom)
        if self.consolidation_fn:
            summary = await self.consolidation_fn(consolidation_prompt)
        else:
            # Default: use lightweight LLM for consolidation
            summary = await self._default_consolidate(consolidation_prompt)
        
        # Append to archive
        if self.consolidated_archive:
            self.consolidated_archive += f"\n\n{summary}"
        else:
            self.consolidated_archive = summary
        
        # Optional: trim archive if it grows too large
        # (re-consolidation or semantic retrieval from external store)
    
    async def _default_consolidate(self, prompt: str) -> str:
        """Default consolidation using a lightweight LLM"""
        # Placeholder: replace with actual LLM call
        # Example: await llm_call(model="gpt-4o-mini", prompt=prompt)
        return "[Summary of turns would go here]"
    
    def get_context(self, system_prompt: str, user_profile: str = "") -> str:
        """
        Build full context for LLM with immutable + archive + verbatim.
        """
        parts = [system_prompt]
        
        if user_profile:
            parts.append(f"\n## User Profile\n{user_profile}")
        
        if self.consolidated_archive:
            parts.append(f"\n## Earlier Conversation (Summarized)\n{self.consolidated_archive}")
        
        parts.append("\n## Recent Conversation")
        for msg in self.verbatim:
            parts.append(f"{msg.role.upper()}: {msg.content}")
        
        return "\n".join(parts)
    
    def get_token_estimate(self) -> dict:
        """Estimate token usage across zones for monitoring"""
        # Rough estimate: 1 token ≈ 4 characters
        return {
            "archive_tokens": len(self.consolidated_archive) // 4,
            "verbatim_tokens": sum(len(m.content) for m in self.verbatim) // 4,
            "total_messages": len(self.verbatim),
            "consolidation_count": self.turn_counter // self.consolidation_batch_size
        }


# Usage example
async def conversation_loop():
    """
    Example conversation loop with sliding context window.
    """
    memory = ConversationMemory(
        verbatim_window_size=10,
        consolidation_batch_size=5,
        consolidation_fn=lambda p: llm_call(model="gpt-4o-mini", prompt=p)
    )
    
    system_prompt = "You are a helpful AI assistant. Maintain context from earlier in the conversation."
    user_profile = "User: Alex, Software Engineer, prefers concise technical explanations"
    
    # Simulate conversation
    turns = [
        ("user", "I'm working on a Python async application"),
        ("assistant", "Great! What aspect of async Python would you like help with?"),
        ("user", "I need to understand asyncio.gather vs asyncio.wait"),
        # ... many more turns ...
    ]
    
    for role, content in turns:
        await memory.add_turn(role, content)
        
        # Build context for next response
        if role == "user":
            context = memory.get_context(system_prompt, user_profile)
            # response = await llm_call(prompt=context)
            # await memory.add_turn("assistant", response)
    
    # Monitor memory usage
    stats = memory.get_token_estimate()
    print(f"Archive: {stats['archive_tokens']} tokens, "
          f"Verbatim: {stats['verbatim_tokens']} tokens, "
          f"Consolidations: {stats['consolidation_count']}")
```

## Tool Landscape

| Tool | Type | Notes |
|------|------|-------|
| LangChain ConversationBufferWindowMemory | Open-source | Sliding window without consolidation; naive truncation of old turns |
| LangChain ConversationSummaryMemory | Open-source | Full-history summarization; lacks verbatim window for recent context |
| LlamaIndex ChatMemoryBuffer | Open-source | Token-based truncation; can be extended with custom consolidation |
| Mem0 | Managed service | Extracts entities and facts from conversations; stores in vector DB for retrieval |
| Custom implementation | DIY | Necessary for fine-grained control over consolidation timing and strategy |

## Related Patterns

- **[Context Compaction](../cost-and-efficiency/context-compaction.md)** — Context compaction summarizes any text to fit budget; sliding window applies compaction specifically to conversation history with zone-based strategy.
- **[Cascading Context Assembly](../cost-and-efficiency/cascading-context-assembly.md)** — Cascading assembly retrieves context on-demand; sliding window maintains full conversation context with compression.
- **[Token Budget](../cost-and-efficiency/token-budget.md)** — Token budget caps total context size; sliding window is a strategy to stay within budget for long conversations.
- **[Hybrid Search](hybrid-search.md)** — For very long conversations (100+ turns), store consolidated archive in vector DB and retrieve relevant segments instead of including entire archive in context.

## Further Reading

- [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) — Research on hierarchical memory management for LLMs
- [Recursively Summarizing Books with Human Feedback](https://arxiv.org/abs/2109.10862) — Anthropic research on hierarchical summarization
- [LangChain Memory Types](https://python.langchain.com/docs/modules/memory/types/) — Overview of conversation memory patterns
- [Building LLM Applications for Production](https://huyenchip.com/2023/04/11/llm-engineering.html) — Chip Huyen's guide, section on context management
