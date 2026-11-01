import Link from 'next/link'
import { patterns } from '@/.velite'
import { PILLAR_ORDER, PILLAR_LABELS, PILLAR_DESCRIPTIONS } from '@/lib/patterns'
import { countTests } from '@/lib/examples'
import { REPO_URL } from '@/lib/site'

const PROBLEMS: { problem: string; slugs: string[] }[] = [
  {
    problem: 'Our LLM bill is too high',
    slugs: ['inference-and-serving/semantic-caching', 'inference-and-serving/model-router', 'cost-and-efficiency/effort-scaling'],
  },
  {
    problem: 'The RAG answers are wrong',
    slugs: ['retrieval-and-memory/hybrid-search', 'retrieval-and-memory/retrieval-quality-gate', 'retrieval-and-memory/grounding-verifier'],
  },
  {
    problem: 'The provider had a bad day, and so did we',
    slugs: ['reliability/circuit-breaker', 'reliability/request-hedging', 'reliability/uncertainty-triggered-retry'],
  },
  {
    problem: 'Our agent never knows when to stop',
    slugs: ['loop-engineering/loop-termination', 'loop-engineering/no-progress-detection', 'loop-engineering/maker-verifier-split'],
  },
  {
    problem: 'A prompt change broke production',
    slugs: ['observability-and-evaluation/prompt-mutation-testing', 'observability-and-evaluation/shadow-model-evaluation', 'governance/prompt-canary-deployment'],
  },
  {
    problem: 'A web page could hijack our agent',
    slugs: ['security-and-trust/tool-output-firewall', 'security-and-trust/guardrails', 'governance/human-in-the-loop'],
  },
]

const PROMISES = [
  {
    title: 'Tested, not just described',
    body: 'Every pattern has a small, dependency-free Python implementation with tests that run offline in CI. The code on the page is copied from those files, so it can’t drift.',
  },
  {
    title: 'When NOT to use it',
    body: 'Each page says where the pattern is the wrong tool. That section saves more engineering time than the rest of the page.',
  },
  {
    title: 'How it fails',
    body: 'Failure modes that show up even when the pattern is built correctly, and the test that checks for each one.',
  },
]

function titleFor(slug: string) {
  return patterns.find((p) => p.slug === slug)?.title ?? slug
}

export default function Home() {
  const tests = countTests()
  const pillarCounts = PILLAR_ORDER.reduce<Record<string, number>>((acc, p) => {
    acc[p] = patterns.filter((pat) => pat.pillar === p).length
    return acc
  }, {})

  return (
    <main>
      {/* Hero */}
      <section className="max-w-screen-xl mx-auto px-6 pt-16 sm:pt-24 pb-16 grid lg:grid-cols-[1.1fr_1fr] gap-12 items-center">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-emerald-200 dark:border-emerald-900 bg-emerald-50 dark:bg-emerald-950/40 px-3 py-1 text-xs font-medium text-emerald-700 dark:text-emerald-300 mb-6">
            <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" aria-hidden />
            {patterns.length} patterns · {tests} passing tests · MIT
          </p>
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-gray-900 dark:text-gray-50 leading-[1.1] mb-5">
            Production LLM patterns
            <br />
            <span className="text-[var(--accent)]">you can run.</span>
          </h1>
          <p className="text-lg text-gray-600 dark:text-gray-400 max-w-xl leading-relaxed mb-8">
            Caching, routing, guardrails, evals and agent loops. Each pattern explains when not to use it and how it fails,
            and ships with a tested reference implementation you can run in under a minute.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/patterns"
              className="inline-flex items-center rounded-lg bg-[var(--accent)] px-5 py-2.5 text-sm font-semibold text-white hover:opacity-90 transition-opacity"
            >
              Browse patterns
            </Link>
            <Link
              href="/guides/decision-guide"
              className="inline-flex items-center rounded-lg border border-gray-300 dark:border-gray-700 px-5 py-2.5 text-sm font-semibold text-gray-800 dark:text-gray-200 hover:border-gray-400 dark:hover:border-gray-500 transition-colors"
            >
              Start from your problem
            </Link>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-semibold text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 transition-colors"
            >
              ★ Star on GitHub
            </a>
          </div>
        </div>

        <div className="rounded-xl border border-gray-800 bg-gray-950 shadow-2xl shadow-violet-500/10 overflow-hidden text-left">
          <div className="flex items-center gap-1.5 px-4 py-3 border-b border-gray-800">
            <span className="h-3 w-3 rounded-full bg-gray-700" />
            <span className="h-3 w-3 rounded-full bg-gray-700" />
            <span className="h-3 w-3 rounded-full bg-gray-700" />
            <span className="ml-3 text-xs text-gray-500 font-mono">examples/</span>
          </div>
          <pre className="p-5 text-[13px] leading-6 font-mono text-gray-300 overflow-x-auto">
            <span className="text-gray-500">$</span> pip install pytest{'\n'}
            <span className="text-gray-500">$</span> pytest reliability/test_circuit_breaker.py -v{'\n'}
            <span className="text-emerald-400">PASSED</span> test_trips_once_failure_rate_crosses_threshold{'\n'}
            <span className="text-emerald-400">PASSED</span> test_a_short_burst_below_min_calls_does_not_trip{'\n'}
            <span className="text-emerald-400">PASSED</span> test_open_circuit_skips_the_primary_entirely{'\n'}
            <span className="text-emerald-400">PASSED</span> test_half_open_probes_close_the_circuit_after_cooldown{'\n'}
            <span className="text-emerald-400">PASSED</span> test_slow_answers_are_returned_but_count_as_failures{'\n'}
            <span className="text-gray-500">…</span>{'\n'}
            <span className="text-emerald-400">7 passed</span> <span className="text-gray-500">in 0.02s · no API key needed</span>
          </pre>
        </div>
      </section>

      {/* Promises */}
      <section className="border-y border-gray-200 dark:border-gray-800 bg-gray-50/60 dark:bg-gray-900/40">
        <div className="max-w-screen-xl mx-auto px-6 py-14 grid md:grid-cols-3 gap-8">
          {PROMISES.map((p) => (
            <div key={p.title}>
              <h2 className="font-semibold text-gray-900 dark:text-gray-50 mb-2">{p.title}</h2>
              <p className="text-sm text-gray-600 dark:text-gray-400 leading-relaxed">{p.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Start from a problem */}
      <section className="max-w-screen-xl mx-auto px-6 py-16">
        <div className="flex items-end justify-between gap-4 mb-8 flex-wrap">
          <div>
            <h2 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-50">Start from your problem</h2>
            <p className="text-gray-500 dark:text-gray-400 mt-1">Nobody needs all {patterns.length}. Pick the symptom you have today.</p>
          </div>
          <Link href="/guides/decision-guide" className="text-sm font-medium text-[var(--accent)] hover:underline">
            Full decision guide →
          </Link>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {PROBLEMS.map(({ problem, slugs }) => (
            <div key={problem} className="rounded-xl border border-gray-200 dark:border-gray-800 p-5">
              <p className="font-semibold text-gray-900 dark:text-gray-50 mb-3">&ldquo;{problem}&rdquo;</p>
              <ul className="space-y-1.5">
                {slugs.map((slug) => (
                  <li key={slug}>
                    <Link
                      href={`/patterns/${slug}`}
                      className="text-sm text-gray-600 dark:text-gray-400 hover:text-[var(--accent)] transition-colors"
                    >
                      → {titleFor(slug)}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* Pillars */}
      <section className="max-w-screen-xl mx-auto px-6 pb-20">
        <h2 className="text-2xl font-bold tracking-tight text-gray-900 dark:text-gray-50 mb-8">Browse by pillar</h2>
        <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {PILLAR_ORDER.map((pillar) => (
            <Link
              key={pillar}
              href={`/patterns?pillar=${pillar}`}
              className="group flex flex-col rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-900 p-4 hover:border-violet-300 dark:hover:border-violet-700 transition-colors"
            >
              <span className="text-xs font-semibold tabular-nums text-[var(--accent)] mb-1">
                {pillarCounts[pillar] ?? 0} patterns
              </span>
              <span className="font-semibold text-gray-900 dark:text-gray-100 group-hover:text-[var(--accent)] transition-colors leading-snug mb-1">
                {PILLAR_LABELS[pillar]}
              </span>
              <span className="text-xs text-gray-500 dark:text-gray-400 leading-relaxed">{PILLAR_DESCRIPTIONS[pillar]}</span>
            </Link>
          ))}
        </div>
      </section>

      {/* Contribute */}
      <section className="max-w-screen-xl mx-auto px-6 pb-24">
        <div className="rounded-2xl bg-gray-900 dark:bg-gray-900 border border-gray-800 px-8 py-10 sm:flex items-center justify-between gap-8">
          <div className="mb-6 sm:mb-0">
            <h2 className="text-xl font-bold text-white mb-2">Run one of these in production?</h2>
            <p className="text-gray-400 max-w-xl">
              Send a field report, fix a failure mode we missed, or add a pattern. The bar is a page plus a runnable example with tests.
            </p>
          </div>
          <a
            href={`${REPO_URL}/blob/main/CONTRIBUTING.md`}
            target="_blank"
            rel="noopener noreferrer"
            className="shrink-0 inline-flex items-center rounded-lg bg-white px-5 py-2.5 text-sm font-semibold text-gray-900 hover:bg-gray-100 transition-colors"
          >
            How to contribute
          </a>
        </div>
      </section>
    </main>
  )
}
