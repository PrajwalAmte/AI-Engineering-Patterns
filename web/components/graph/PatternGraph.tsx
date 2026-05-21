'use client'

import { useEffect, useRef } from 'react'
import { useRouter } from 'next/navigation'

const PILLARS: Record<string, { label: string; color: string }> = {
  'inference-and-serving': { label: 'Inference & Serving', color: '#818cf8' },
  'data-patterns': { label: 'Data Patterns', color: '#fbbf24' },
  'reliability': { label: 'Reliability', color: '#f87171' },
  'retrieval-and-memory': { label: 'Retrieval & Memory', color: '#34d399' },
  'observability': { label: 'Observability', color: '#a78bfa' },
  'security-and-trust': { label: 'Security & Trust', color: '#fb923c' },
  'cost-and-efficiency': { label: 'Cost & Efficiency', color: '#22d3ee' },
  'governance': { label: 'Governance', color: '#f472b6' },
  'graph-patterns': { label: 'Graph Patterns', color: '#2dd4bf' },
  'evaluation-and-testing': { label: 'Evaluation & Testing', color: '#a3e635' },
}

interface PatternDef {
  id: string
  label: string
  pillar: string
  path: string
}

const PATTERNS: PatternDef[] = [
  { id: 'llm-gateway', label: 'LLM Gateway', pillar: 'inference-and-serving', path: 'inference-and-serving/llm-gateway' },
  { id: 'model-router', label: 'Model Router', pillar: 'inference-and-serving', path: 'inference-and-serving/model-router' },
  { id: 'semantic-caching', label: 'Semantic Caching', pillar: 'inference-and-serving', path: 'inference-and-serving/semantic-caching' },
  { id: 'data-contract', label: 'Data Contract', pillar: 'data-patterns', path: 'data-patterns/data-contract' },
  { id: 'semantic-dedup', label: 'Semantic Dedup', pillar: 'data-patterns', path: 'data-patterns/semantic-deduplication' },
  { id: 'circuit-breaker', label: 'Circuit Breaker', pillar: 'reliability', path: 'reliability/circuit-breaker' },
  { id: 'hybrid-search', label: 'Hybrid Search', pillar: 'retrieval-and-memory', path: 'retrieval-and-memory/hybrid-search' },
  { id: 'freshness-watermark', label: 'Freshness Watermark', pillar: 'retrieval-and-memory', path: 'retrieval-and-memory/retrieval-freshness-watermark' },
  { id: 'span-level-tracing', label: 'Span-Level Tracing', pillar: 'observability', path: 'observability/span-level-tracing' },
  { id: 'embedding-drift', label: 'Embedding Drift', pillar: 'observability', path: 'observability/embedding-drift-detector' },
  { id: 'input-sanitization', label: 'Input Sanitization', pillar: 'security-and-trust', path: 'security-and-trust/input-sanitization' },
  { id: 'tool-output-firewall', label: 'Tool Output Firewall', pillar: 'security-and-trust', path: 'security-and-trust/tool-output-firewall' },
  { id: 'token-budget', label: 'Token Budget', pillar: 'cost-and-efficiency', path: 'cost-and-efficiency/token-budget' },
  { id: 'cascading-context', label: 'Cascading Context', pillar: 'cost-and-efficiency', path: 'cost-and-efficiency/cascading-context-assembly' },
  { id: 'model-card', label: 'Model Card', pillar: 'governance', path: 'governance/model-card' },
  { id: 'canary-deployment', label: 'Canary Deployment', pillar: 'governance', path: 'governance/prompt-canary-deployment' },
  { id: 'graph-rag', label: 'GraphRAG', pillar: 'graph-patterns', path: 'graph-patterns/graph-rag' },
  { id: 'graph-of-thoughts', label: 'Graph of Thoughts', pillar: 'graph-patterns', path: 'graph-patterns/graph-of-thoughts' },
  { id: 'entity-resolution', label: 'Entity Resolution', pillar: 'graph-patterns', path: 'graph-patterns/entity-resolution-graph' },
  { id: 'llm-as-judge', label: 'LLM-as-Judge', pillar: 'evaluation-and-testing', path: 'evaluation-and-testing/llm-as-judge' },
]

const LINKS: [string, string][] = [
  ['llm-gateway', 'model-router'],
  ['llm-gateway', 'semantic-caching'],
  ['model-router', 'semantic-caching'],
  ['llm-gateway', 'span-level-tracing'],
  ['llm-gateway', 'circuit-breaker'],
  ['llm-gateway', 'input-sanitization'],
  ['model-router', 'token-budget'],
  ['semantic-caching', 'token-budget'],
  ['cascading-context', 'token-budget'],
  ['graph-rag', 'hybrid-search'],
  ['graph-rag', 'entity-resolution'],
  ['graph-rag', 'graph-of-thoughts'],
  ['graph-of-thoughts', 'entity-resolution'],
  ['entity-resolution', 'data-contract'],
  ['data-contract', 'semantic-dedup'],
  ['model-card', 'data-contract'],
  ['llm-as-judge', 'span-level-tracing'],
  ['llm-as-judge', 'circuit-breaker'],
  ['llm-as-judge', 'model-card'],
  ['embedding-drift', 'span-level-tracing'],
  ['freshness-watermark', 'hybrid-search'],
  ['tool-output-firewall', 'input-sanitization'],
  ['canary-deployment', 'model-card'],
]

interface Node extends PatternDef {
  color: string
  x: number
  y: number
  vx: number
  vy: number
}

export function PatternGraph() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const legendRef = useRef<HTMLDivElement>(null)
  const tooltipRef = useRef<HTMLDivElement>(null)
  const router = useRouter()

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId = 0

    function init() {
      if (!canvas || !ctx) return
      cancelAnimationFrame(animId)

      const legendEl = legendRef.current
      const tooltipEl = tooltipRef.current

      if (legendEl) {
        legendEl.innerHTML = ''
        for (const [, { label, color }] of Object.entries(PILLARS)) {
          const span = document.createElement('span')
          span.className = 'inline-flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400'
          span.innerHTML = `<i style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${color};flex-shrink:0"></i>${label}`
          legendEl.appendChild(span)
        }
      }

      const dpr = window.devicePixelRatio || 1
      const rect = canvas.getBoundingClientRect()
      const W = rect.width
      const H = rect.height
      canvas.width = W * dpr
      canvas.height = H * dpr
      ctx.scale(dpr, dpr)

      const isDark = document.documentElement.classList.contains('dark')
      const textColor = isDark ? 'rgba(210,210,220,0.9)' : 'rgba(30,30,40,0.85)'
      const textDim = isDark ? 'rgba(210,210,220,0.2)' : 'rgba(30,30,40,0.18)'
      const edgeColor = isDark ? 'rgba(140,140,160,0.18)' : 'rgba(100,100,120,0.15)'
      const edgeHi = isDark ? 'rgba(129,140,248,0.55)' : 'rgba(99,102,241,0.5)'

      const NODE_R = 18

      const nodes: Node[] = PATTERNS.map((p) => ({
        ...p,
        color: PILLARS[p.pillar]?.color ?? '#888',
        x: W / 2 + (Math.random() - 0.5) * W * 0.5,
        y: H / 2 + (Math.random() - 0.5) * H * 0.5,
        vx: 0,
        vy: 0,
      }))

      const nodeMap: Record<string, Node> = {}
      nodes.forEach((n) => { nodeMap[n.id] = n })

      const adj: Record<string, Set<string>> = {}
      nodes.forEach((n) => { adj[n.id] = new Set() })
      for (const [s, t] of LINKS) {
        adj[s]?.add(t)
        adj[t]?.add(s)
      }

      let hovered: Node | null = null
      let dragged: Node | null = null
      let didDrag = false

      function step() {
        for (let i = 0; i < nodes.length; i++) {
          for (let j = i + 1; j < nodes.length; j++) {
            const a = nodes[i], b = nodes[j]
            const dx = b.x - a.x, dy = b.y - a.y
            const d2 = dx * dx + dy * dy + 1
            const d = Math.sqrt(d2)
            const f = 3500 / d2
            const fx = (f * dx) / d, fy = (f * dy) / d
            a.vx -= fx; a.vy -= fy
            b.vx += fx; b.vy += fy
          }
        }
        for (const [s, t] of LINKS) {
          const a = nodeMap[s], b = nodeMap[t]
          if (!a || !b) continue
          const dx = b.x - a.x, dy = b.y - a.y
          const d = Math.sqrt(dx * dx + dy * dy) + 0.01
          const f = 0.004 * d
          a.vx += (f * dx) / d; a.vy += (f * dy) / d
          b.vx -= (f * dx) / d; b.vy -= (f * dy) / d
        }
        for (const n of nodes) {
          n.vx += (W / 2 - n.x) * 0.01
          n.vy += (H / 2 - n.y) * 0.01
          n.vx *= 0.88; n.vy *= 0.88
          if (n !== dragged) {
            n.x += n.vx; n.y += n.vy
            n.x = Math.max(NODE_R, Math.min(W - NODE_R, n.x))
            n.y = Math.max(NODE_R, Math.min(H - NODE_R, n.y))
          }
        }
      }

      function render() {
        if (!ctx) return
        ctx.clearRect(0, 0, W, H)
        for (const [s, t] of LINKS) {
          const a = nodeMap[s], b = nodeMap[t]
          if (!a || !b) continue
          const hi = hovered != null && (a.id === hovered.id || b.id === hovered.id)
          ctx.beginPath()
          ctx.moveTo(a.x, a.y)
          ctx.lineTo(b.x, b.y)
          ctx.strokeStyle = hi ? edgeHi : edgeColor
          ctx.lineWidth = hi ? 2.5 : 1
          ctx.stroke()
        }
        for (const n of nodes) {
          const isH = hovered === n
          const isC = hovered != null && adj[hovered.id]?.has(n.id)
          const dim = hovered != null && !isH && !isC
          const r = isH ? NODE_R + 4 : NODE_R
          ctx.save()
          ctx.globalAlpha = dim ? 0.2 : 1
          if (isH) { ctx.shadowColor = n.color; ctx.shadowBlur = 14 }
          ctx.beginPath()
          ctx.arc(n.x, n.y, r, 0, Math.PI * 2)
          ctx.fillStyle = n.color
          ctx.fill()
          ctx.shadowBlur = 0
          ctx.strokeStyle = isH ? '#fff' : 'rgba(255,255,255,0.15)'
          ctx.lineWidth = isH ? 2.5 : 0.5
          ctx.stroke()
          ctx.font = `${isH ? 'bold ' : ''}11px system-ui, -apple-system, sans-serif`
          ctx.textAlign = 'center'
          ctx.fillStyle = dim ? textDim : textColor
          ctx.fillText(n.label, n.x, n.y + r + 14)
          ctx.restore()
        }
      }

      function findNode(x: number, y: number): Node | null {
        for (let i = nodes.length - 1; i >= 0; i--) {
          const n = nodes[i]
          const dx = x - n.x, dy = y - n.y
          if (dx * dx + dy * dy <= (NODE_R + 6) * (NODE_R + 6)) return n
        }
        return null
      }

      function getPos(e: MouseEvent): [number, number] {
        const r = canvas!.getBoundingClientRect()
        return [e.clientX - r.left, e.clientY - r.top]
      }

      canvas.onmousemove = (e: MouseEvent) => {
        const [mx, my] = getPos(e)
        if (dragged) {
          dragged.x = mx; dragged.y = my
          dragged.vx = 0; dragged.vy = 0
          didDrag = true
        }
        const found = findNode(mx, my)
        if (found !== hovered) {
          hovered = found
          canvas!.style.cursor = found ? 'pointer' : (dragged ? 'grabbing' : 'default')
          if (found && tooltipEl) {
            tooltipEl.style.display = 'block'
            tooltipEl.textContent = `${found.label} — ${PILLARS[found.pillar]?.label}`
          } else if (tooltipEl) {
            tooltipEl.style.display = 'none'
          }
        }
        if (hovered && tooltipEl) {
          tooltipEl.style.left = `${mx + 14}px`
          tooltipEl.style.top = `${my - 32}px`
        }
      }

      canvas.onmousedown = (e: MouseEvent) => {
        const [mx, my] = getPos(e)
        const found = findNode(mx, my)
        if (found) {
          dragged = found
          didDrag = false
          canvas!.style.cursor = 'grabbing'
        }
      }

      canvas.onmouseup = () => {
        dragged = null
        canvas!.style.cursor = hovered ? 'pointer' : 'default'
      }

      canvas.onclick = () => {
        if (!didDrag && hovered) {
          router.push(`/patterns/${hovered.path}`)
        }
      }

      canvas.onmouseleave = () => {
        hovered = null
        dragged = null
        if (tooltipEl) tooltipEl.style.display = 'none'
      }

      function animate() {
        step()
        render()
        animId = requestAnimationFrame(animate)
      }
      animate()
    }

    const ro = new ResizeObserver(() => init())
    ro.observe(canvas)
    init()

    return () => {
      cancelAnimationFrame(animId)
      ro.disconnect()
      if (canvasRef.current) {
        canvasRef.current.onmousemove = null
        canvasRef.current.onmousedown = null
        canvasRef.current.onmouseup = null
        canvasRef.current.onclick = null
        canvasRef.current.onmouseleave = null
      }
    }
  }, [router])

  return (
    <div className="relative w-full rounded-lg border border-gray-200 dark:border-gray-800 overflow-hidden bg-white dark:bg-gray-950">
      <div
        ref={legendRef}
        className="flex flex-wrap gap-3 px-4 py-3 border-b border-gray-200 dark:border-gray-800"
      />
      <canvas
        ref={canvasRef}
        className="block w-full"
        style={{ height: 560 }}
      />
      <div
        ref={tooltipRef}
        className="hidden absolute pointer-events-none z-10 px-2.5 py-1.5 text-xs rounded-md border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 shadow-md whitespace-nowrap"
      />
    </div>
  )
}
