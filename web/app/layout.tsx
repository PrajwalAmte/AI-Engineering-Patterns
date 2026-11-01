import type { Metadata } from 'next'
import { Geist, Geist_Mono } from 'next/font/google'
import { ThemeProvider } from '@/components/ThemeProvider'
import { Navbar } from '@/components/layout/Navbar'
import { Footer } from '@/components/layout/Footer'
import { OG_IMAGE, SITE_DESCRIPTION, SITE_NAME, SITE_TAGLINE, SITE_URL } from '@/lib/site'
import './globals.css'

const geistSans = Geist({ variable: '--font-geist-sans', subsets: ['latin'] })
const geistMono = Geist_Mono({ variable: '--font-geist-mono', subsets: ['latin'] })

// Optional, privacy-friendly analytics. Set NEXT_PUBLIC_GOATCOUNTER_URL at build time
// (e.g. https://yourname.goatcounter.com/count) to turn it on; unset means no tracking.
const GOATCOUNTER_URL = process.env.NEXT_PUBLIC_GOATCOUNTER_URL

export const metadata: Metadata = {
  metadataBase: new URL(`${SITE_URL}/`),
  title: {
    default: `${SITE_NAME}: ${SITE_TAGLINE}`,
    template: `%s · ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  keywords: [
    'LLM engineering patterns',
    'production LLM',
    'RAG patterns',
    'AI agents',
    'LLM guardrails',
    'LLM evaluation',
    'AI system design',
    'LLMOps',
  ],
  openGraph: {
    type: 'website',
    siteName: SITE_NAME,
    title: `${SITE_NAME}: ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
    url: `${SITE_URL}/`,
    images: [OG_IMAGE],
  },
  twitter: {
    card: 'summary_large_image',
    title: `${SITE_NAME}: ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
    images: [OG_IMAGE.url],
  },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
      suppressHydrationWarning
    >
      <body className="min-h-full flex flex-col bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-50">
        <ThemeProvider>
          <Navbar />
          <div className="flex-1">{children}</div>
          <Footer />
        </ThemeProvider>
        {GOATCOUNTER_URL && (
          <script data-goatcounter={GOATCOUNTER_URL} async src="https://gc.zgo.at/count.js" />
        )}
      </body>
    </html>
  )
}
