import type { Metadata } from 'next'
import { JetBrains_Mono } from 'next/font/google'
import './globals.css'

const mono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-mono',
  weight: ['400', '500', '600', '700'],
})

export const metadata: Metadata = {
  title: 'Polymarket Scanner',
  description: 'AI-powered Polymarket mispricing scanner. Paste a URL, get the alpha.',
  openGraph: {
    title: 'Polymarket Scanner',
    description: 'AI-powered Polymarket mispricing scanner.',
    type: 'website',
  },
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className={`${mono.variable} h-full`}>
      <body className="min-h-full flex flex-col bg-[#0a0a0a] text-[#f1f5f9] antialiased font-mono">
        {children}
      </body>
    </html>
  )
}
