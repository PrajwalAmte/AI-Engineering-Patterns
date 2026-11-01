# Contributing to AI Engineering Patterns

Thank you for contributing. This project exists because of community participation.

## Ways to Contribute

### Propose a New Pattern

1. Open a GitHub Issue using the **New Pattern** template.
2. Fill in: pattern name, which pillar it belongs to, and a brief description of the problem it solves.
3. A maintainer will triage and label it.

### Write a Pattern

1. Fork the repository and create a branch from `main`.
2. Write the example first: `examples/<pillar_with_underscores>/<pattern_name>.py` plus `test_<pattern_name>.py` next to it. Standard library only; use `examples/common/fakes.py` for models, embeddings and time. The tests should cover the failure modes the page describes, not just the happy path.
3. Create the page in the correct pillar directory under `content/patterns/`, following the template below. Set `example:` in the frontmatter and put an empty marker block in the Implementation Example section:

   ```markdown
   <!-- example: examples/reliability/circuit_breaker.py -->
   <!-- /example -->
   ```

4. Run `node scripts/sync-examples.js` to copy the code into the page, then `node scripts/validate-schema.js` and `cd examples && pytest`.
5. Open a Pull Request. Maintainers will review for accuracy, completeness, neutrality, and fit.

### Improve an Existing Pattern

Open an Issue using the **Improve Pattern** template, or submit a PR directly with your changes.

## Pattern Template

Every pattern must include this frontmatter:

```yaml
---
title: "Pattern Name"
pillar: "pillar-slug"
status: "proposed"
tags: ["tag-one", "tag-two"]
related:
  - "Related Pattern Name"   # must match another pattern's title exactly
example: examples/<pillar>/<pattern>.py
contributors: ["@yourgithub"]
last_updated: "2026-11"
description: "One-line description for SEO and pattern cards."
---
```

Valid pillar slugs: `inference-and-serving`, `data-patterns`, `reliability`, `retrieval-and-memory`, `observability-and-evaluation`, `security-and-trust`, `cost-and-efficiency`, `governance`, `graph-patterns`, `loop-engineering`.

Valid status values: `proposed`, `emerging`, `validated-in-production`.

### Required Sections (in order)

1. **What It Is** — One paragraph. Plain language.
2. **The Problem It Solves** — What breaks or costs too much without this pattern.
3. **How It Works** — Step-by-step mechanism. Diagrams where useful.
4. **When to Use It** — Specific conditions and workload types.
5. **When NOT to Use It** — Explicit anti-use-cases. This section is mandatory.
6. **Trade-offs** — 2-4 honest trade-offs. No pattern is free.
7. **Failure Modes** — How the pattern breaks even when implemented correctly, and what to do about it.
8. **Implementation Example** — One or two sentences, the `pytest` command, and the synced example block. Never hand-written code that isn't tested.
9. **Tool Landscape** — Which tools implement or support this pattern (vendor-neutral).
10. **Related Patterns** — Relative links to other pattern files, e.g. `[Guardrails](../security-and-trust/guardrails.md)`.
11. **Further Reading** — 2-4 primary references (papers, official docs, first-hand engineering posts). Every link must be one you have opened. No affiliate links.

## Quality Bar

All patterns must:

- Be tool-agnostic and vendor-neutral in the "What It Is" and "How It Works" sections.
- Include at least one concrete trade-off.
- Include a "When NOT to Use It" section.
- Be written for a practitioner, not a researcher.
- Say plainly when the pattern name is ours rather than an established term.
- Claim `validated-in-production` only when the technique is widely used, not just plausible.
- Contain no statistics without a cited source.

Patterns are rejected if they:

- Are marketing material for a specific vendor.
- Duplicate an existing entry without meaningfully extending it.
- Lack the "When NOT to Use It" section.
- Ship without a runnable, tested example.

## Status Labels

| Status | Meaning |
|---|---|
| `proposed` | Pattern identified, not yet validated |
| `emerging` | Used in practice by early adopters, trade-offs still being understood |
| `validated-in-production` | Widely used by multiple teams, trade-offs well understood |

## Development Setup

```bash
cd web
npm install
npm run dev
```

The site runs at `http://localhost:3000`.

## Checks

CI runs all of these. Run them locally before opening a PR:

```bash
cd examples && pytest && cd ..          # every example's tests
node scripts/sync-examples.js --check    # pages show the tested code
node scripts/validate-schema.js          # frontmatter, related names, internal links
```

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
