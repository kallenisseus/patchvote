/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "../../main/templates/**/*.html",
    "../../templates/**/*.html",
    "../../**/templates/**/*.html",
    "../../**/*.py",
    "../../**/*.js",
  ],
  theme: {
    extend: {},
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        patchvoting: {
          // Map your old CSS variables to daisyUI theme slots
          // Old: --bg #0f1115, --bg-soft #151822, --panel #1b1f2b, --border #2a2f3e, --accent #5c7cfa :contentReference[oaicite:2]{index=2}
          "base-100": "#151822", // surfaces/cards
          "base-200": "#0f1115", // page background
          "base-300": "#2a2f3e", // borders/dividers
          "base-content": "#e6e8ef",

          primary: "#5c7cfa",
          "primary-content": "#ffffff",

          success: "#37b24d",
          error: "#f03e3e",
          warning: "#f59f00",
          info: "#74c0fc",

          neutral: "#1b1f2b",
          "neutral-content": "#e6e8ef",
        },
      },
      "dark",
      "light",
    ],
  },
};
