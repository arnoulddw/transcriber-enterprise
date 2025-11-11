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

        // Semantic aliases so templates stay descriptive
        'surface': '#ffffff',
        'surface-alt': '#fefefe',
        'surface-muted': '#f3f4f6',
        'border-default': '#e5e7eb',
        'border-strong': '#d1d5db',
        'text-muted': '#6b7280',
        'text-strong': '#111827',
        'accent': '#5c6ac4',
        'accent-soft': '#eef2ff',
        'accent-border': '#c7d2fe',
        'danger': '#d32f2f',
        'warning': '#ffb347',
        'success': '#2e7d32',
        'info': '#1976d2',
        'workflow-label': {
          'default': '#ffffff',
          'pink': '#ffd1dc',
          'bluegray': '#aec6cf',
          'mint': '#cfffd1',
          'lemon': '#fffacd',
          'lavender': '#e6e6fa',
          'orange': '#ffb347',
        },
      },
      fontFamily: {
        // Using a common system font stack similar to Materialize
        sans: ['-apple-system', 'BlinkMacSystemFont', '"Segoe UI"', 'Roboto', '"Helvetica Neue"', 'Arial', 'sans-serif', ...defaultTheme.fontFamily.sans],
        // Add 'mono' if you use monospace fonts, e.g., for code blocks
        // mono: ['Courier New', 'Courier', 'monospace', ...defaultTheme.fontFamily.mono],
      },
      fontSize: {
        'xs': ['0.75rem', { lineHeight: '1.1rem' }],
        'sm': ['0.85rem', { lineHeight: '1.3rem' }],
        'base': ['1rem', { lineHeight: '1.5rem' }],
        'lg': ['1.125rem', { lineHeight: '1.65rem' }],
        'xl': ['1.25rem', { lineHeight: '1.75rem' }],
        '2xl': ['1.5rem', { lineHeight: '2rem' }],
      },
      borderRadius: {
        'xs': '0.125rem',
        'sm': '0.25rem',
        'md': '0.5rem',
        'lg': '0.75rem',
        'xl': '1rem',
        'pill': '9999px',
      },
      spacing: {
        '13': '3.25rem',
        '15': '3.75rem',
        '18': '4.5rem',
        '25': '6.25rem',
        '30': '7.5rem',
      },
      boxShadow: {
        'surface': '0 1px 3px rgba(15, 23, 42, 0.1), 0 1px 2px rgba(15, 23, 42, 0.06)',
        'surface-xl': '0 10px 15px rgba(15, 23, 42, 0.15), 0 4px 6px rgba(15, 23, 42, 0.1)',
        'focus': '0 0 0 3px rgba(25, 118, 210, 0.35)',
      },
      maxWidth: {
        'content': '64rem',
        'narrow': '36rem',
      },
      transitionTimingFunction: {
        'swift': 'cubic-bezier(0.4, 0, 0.2, 1)',
      },
      transitionDuration: {
        '250': '250ms',
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
