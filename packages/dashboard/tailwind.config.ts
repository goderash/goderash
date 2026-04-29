import type { Config } from 'tailwindcss'

const config: Config = {
  content: [
    './app/**/*.{ts,tsx}',
    './components/**/*.{ts,tsx}',
    './lib/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        mono: [
          'ui-monospace',
          'SFMono-Regular',
          'JetBrains Mono',
          'Menlo',
          'Monaco',
          'monospace',
        ],
      },
      colors: {
        ink: {
          50: '#fafafa',
          100: '#f4f4f5',
          200: '#e4e4e7',
          400: '#a1a1aa',
          600: '#52525b',
          800: '#27272a',
          900: '#18181b',
        },
        accent: {
          DEFAULT: '#0c4a6e',
          fg: '#0369a1',
        },
        ok: '#16a34a',
        warn: '#ca8a04',
        bad: '#dc2626',
      },
    },
  },
  plugins: [],
}

export default config
