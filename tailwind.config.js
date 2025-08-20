// tailwind.config.js
/** @type {import('tailwindcss').Config} */
const defaultTheme = require('tailwindcss/defaultTheme');

module.exports = {
  content: [
    './app/templates/**/*.html',
    './app/static/js/**/*.js',
  ],
  theme: {
    extend: {
      colors: {
        // Primary Blues (from Materialize blue darken-2, lighten-1)
        'primary': {
          DEFAULT: '#1976d2', // blue darken-2
          light: '#42a5f5',   // blue lighten-1
          dark: '#1565c0',    // for hover states
        },
        // Accent/Secondary Colors (examples, can be adjusted)
        'secondary': {
          DEFAULT: '#ffa000', // orange darken-1 (example for warning)
          light: '#ffb347',
          dark: '#ff8f00',
        },
        // Alert Colors
        'alert-error': '#d32f2f',    // red darken-1
        'alert-success': '#2e7d32',  // green darken-3 (Materialize green darken-1 is #388e3c)
        'alert-warning': '#ffa000',  // orange darken-1
        'alert-info': '#1976d2',     // blue darken-2 (same as primary)

        // Grays (Materialize-like grays)
        'gray': {
          '50': '#fafafa',  // background for some elements
          '100': '#f5f5f5', // light backgrounds, borders
          '200': '#eeeeee', // borders, disabled states
          '300': '#e0e0e0', // borders
          '400': '#bdbdbd', // medium text, icons
          '500': '#9e9e9e', // standard text
          '600': '#757575', // darker text, subheadings
          '700': '#616161', // even darker text
          '800': '#424242', // headings, important text
          '900': '#212121', // very dark text, backgrounds
          '950': '#1a1a1a',
        },
        // Specific colors from main.css
        'body-bg': '#f8f9fa',
        'default-text': '#333',
      },
      fontFamily: {
        // Using a common system font stack similar to Materialize
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif', ...defaultTheme.fontFamily.sans],
        // Add 'mono' if you use monospace fonts, e.g., for code blocks
        // mono: ['Courier New', 'Courier', 'monospace', ...defaultTheme.fontFamily.mono],
      },
      // You can extend spacing, breakpoints, etc. here if needed
      // Example:
      // spacing: {
      //   '128': '32rem',
      // },
      // screens: {
      //   'xs': '480px',
      // },
    },
  },
  plugins: [
    require('@tailwindcss/forms')({
      strategy: 'class', // Or 'base', if you prefer less opinionated form styles
    }),
    require('@headlessui/tailwindcss'), // Added Headless UI plugin
  ],
}