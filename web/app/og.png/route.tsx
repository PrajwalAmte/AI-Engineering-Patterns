import { ImageResponse } from 'next/og'
import { patterns } from '@/.velite'
import { countTests } from '@/lib/examples'

// Exported as out/og.png so GitHub Pages serves it with an image content type.
export const dynamic = 'force-static'

const size = { width: 1200, height: 630 }

export function GET() {
  const tests = countTests()
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between',
          padding: '72px 80px',
          background: '#0b0f17',
          color: '#f3f4f6',
          fontFamily: 'sans-serif',
        }}
      >
        <div style={{ display: 'flex', fontSize: 28, color: '#a78bfa', letterSpacing: 1 }}>AI ENGINEERING PATTERNS</div>
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <div style={{ fontSize: 76, fontWeight: 700, lineHeight: 1.05 }}>Production LLM patterns</div>
          <div style={{ fontSize: 76, fontWeight: 700, lineHeight: 1.05, color: '#8b84ff' }}>you can run.</div>
        </div>
        <div style={{ display: 'flex', gap: 32, fontSize: 28, color: '#9ca3af' }}>
          <span>{patterns.length} patterns</span>
          <span style={{ color: '#34d399' }}>{tests} passing tests</span>
          <span>no API key needed</span>
        </div>
      </div>
    ),
    size,
  )
}
