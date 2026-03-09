/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#08111f',
        card: '#101827',
        line: '#1e293b',
        brand: '#4f46e5',
      },
      boxShadow: {
        card: '0 18px 40px rgba(2, 6, 23, 0.28)',
      },
    },
  },
  plugins: [],
};
