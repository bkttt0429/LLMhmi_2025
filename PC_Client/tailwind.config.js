/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./templates/**/*.html",
        "./static/**/*.js",
    ],
    theme: {
        extend: {
            colors: {
                'cyber-green': '#00ff9d',
                'cyber-dark': '#050505',
            },
            fontFamily: {
                'mono': ['Share Tech Mono', 'monospace'],
            },
        },
    },
    plugins: [],
}
