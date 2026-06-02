/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'energy-bg-primary': '#080E18',
        'energy-bg-secondary': '#0D1829',
        'energy-bg-tertiary': '#111F35',
        'energy-border': '#1E3050',
        'energy-border-bright': '#2A4570',
        'energy-text-primary': '#E8EEF7',
        'energy-text-secondary': '#8BA3C7',
        'energy-text-muted': '#4A6A96',
        'energy-accent-blue': '#3B82F6',
        'energy-accent-cyan': '#06B6D4',
        'energy-bull': '#10B981',
        'energy-bull-dim': '#064E3B',
        'energy-bear': '#EF4444',
        'energy-bear-dim': '#450A0A',
        'energy-neutral': '#6B7280',
        'energy-amber': '#F59E0B',
        'energy-amber-dim': '#451A03',
        'energy-header': '#050B14',
      },
      fontFamily: {
        'mono': ['DM Mono', 'monospace'],
        'sans': ['Inter', 'sans-serif'],
        'bebas': ['Bebas Neue', 'sans-serif'],
      },
      spacing: {
        'xs': '8px',
        'sm': '12px',
        'md': '16px',
        'lg': '24px',
      },
      borderRadius: {
        'card': '6px',
      },
    },
  },
  plugins: [],
}
