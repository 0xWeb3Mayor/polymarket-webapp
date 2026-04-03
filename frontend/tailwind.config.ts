import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: '#0a0a0a',
        surface: '#111318',
        'surface-2': '#16181f',
        border: '#1a1a2e',
        muted: '#94a3b8',
        'signal-strong-buy': '#22c55e',
        'signal-buy': '#86efac',
        'signal-hold': '#94a3b8',
        'signal-sell': '#f97316',
        'signal-strong-sell': '#ef4444',
      },
      fontFamily: {
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config
