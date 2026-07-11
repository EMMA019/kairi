/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        sentinel: {
          bg: "#060A0F",
          card: "#0C1117",
          accent: "#00FF88",
          red: "#FF4466",
          yellow: "#FFB800",
          blue: "#4499FF",
          purple: "#AA66FF",
          gray: "#6B8299",
        }
      },
      fontFamily: {
        mono: ['IBM Plex Mono', 'monospace'],
        sans: ['IBM Plex Sans', 'sans-serif'],
      }
    },
  },
  plugins: [],
}