/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './work_time_reporter/templates/**/*.html',
    './templates/**/*.html',
    './work_time_reporter/static/js/**/*.js',
  ],
  theme: {
    extend: {},
  },
  plugins: [
    require('@tailwindcss/forms'),
  ],
}
