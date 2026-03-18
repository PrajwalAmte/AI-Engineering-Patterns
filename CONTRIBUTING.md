# Contributing to Production AI Patterns

Thank you for contributing. This project exists because of community participation.

## Ways to Contribute

### Propose a New Pattern

1. Open a GitHub Issue using the **New Pattern** template.
2. Fill in: pattern name, which pillar it belongs to, and a brief description of the problem it solves.
3. A maintainer will triage and label it.

### Write a Pattern

1. Fork the repository and create a branch from `main`.
2. Create a new Markdown file in the correct pillar directory under `site/src/content/docs/patterns/`.
3. Follow the pattern template below exactly.
4. Open a Pull Request. Maintainers will review for accuracy, completeness, neutrality, and fit.

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
  - "Related Pattern Name"
contributors: ["@yourgithub"]
last_updated: "2026-03"
description: "One-line description for SEO and pattern cards."
---
```

Valid pillar slugs: `inference-and-serving`, `data-patterns`, `reliability`, `retrieval-and-memory`, `observability`, `security-and-trust`, `cost-and-efficiency`, `governance`.

Valid status values: `proposed`, `emerging`, `validated-in-production`.

### Required Sections (in order)

1. **What It Is** — One paragraph. Plain language.
2. **The Problem It Solves** — What breaks or costs too much without this pattern.
3. **How It Works** — Step-by-step mechanism. Diagrams where useful.
4. **When to Use It** — Specific conditions and workload types.
5. **When NOT to Use It** — Explicit anti-use-cases. This section is mandatory.
6. **Trade-offs** — 2-4 honest trade-offs. No pattern is free.
7. **Implementation Example** — Minimal working code snippet. Python preferred, but language-agnostic is fine.
8. **Tool Landscape** — Which tools implement or support this pattern (vendor-neutral).
9. **Related Patterns** — Links to adjacent or complementary patterns.
10. **Further Reading** — 2-4 high-quality references (papers, posts, docs). No affiliate links.

## Quality Bar

All patterns must:

- Be tool-agnostic and vendor-neutral in the "What It Is" and "How It Works" sections.
- Include at least one concrete trade-off.
- Include a "When NOT to Use It" section.
- Be written for a practitioner, not a researcher.

Patterns are rejected if they:

- Are marketing material for a specific vendor.
- Duplicate an existing entry without meaningfully extending it.
- Lack the "When NOT to Use It" section.

## Status Labels

| Status | Meaning |
|---|---|
| `proposed` | Pattern identified, not yet validated |
| `emerging` | Used in practice by early adopters, trade-offs still being understood |
| `validated-in-production` | Widely used by multiple teams, trade-offs well understood |

## Development Setup

```bash
cd site
npm install
npm run dev
```

The site runs at `http://localhost:4321`.

## Schema Validation

Pattern frontmatter is validated against `schema/pattern.schema.json`. To run validation locally:

```bash
cd scripts
npm install
cd ..
node scripts/validate-schema.js
```

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](CODE_OF_CONDUCT.md). By participating, you agree to uphold it.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
