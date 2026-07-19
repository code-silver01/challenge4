/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fifa: {
          red: '#D50032',
          grass: '#007A33',
        },
        offside: {
          neonGreen: '#39FF14',
          electricBlue: '#00FFFF',
          slate: '#0f172a',
          charcoal: '#171717',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
      }
    },
  },
  plugins: [],
}
