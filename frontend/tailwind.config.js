/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas:       "var(--canvas)",
        surface:      "var(--surface)",
        "surface-2":  "var(--surface-2)",
        "surface-3":  "var(--surface-3)",
        border:       "var(--border)",
        "border-strong": "var(--border-strong)",
        text:         "var(--text)",
        "text-muted": "var(--text-muted)",
        "text-faint": "var(--text-faint)",
        // Accent
        accent:       "var(--accent)",
        "accent-hover":"var(--accent-hover)",
        "accent-soft": "var(--accent-soft)",
        // Backward-compat aliases
        brand:        "var(--accent)",
        "brand-hover":"var(--accent-hover)",
        "brand-soft": "var(--accent-soft)",
        // Status
        ok:           "var(--ok)",
        "ok-bg":      "var(--ok-bg)",
        "ok-border":  "var(--ok-border)",
        warning:      "var(--warning)",
        "warning-bg": "var(--warning-bg)",
        "warning-border": "var(--warning-border)",
        critical:     "var(--critical)",
        "critical-bg":"var(--critical-bg)",
        "critical-border": "var(--critical-border)",
        neutral:      "var(--neutral)",
        "neutral-bg": "var(--neutral-bg)",
        "neutral-border": "var(--neutral-border)",
        // Chart
        "chart-cpu":  "var(--chart-cpu)",
        "chart-mem":  "var(--chart-mem)",
        "chart-disk": "var(--chart-disk)",
        "chart-net":  "var(--chart-net)",
      },
      fontFamily: {
        sans: ["'IBM Plex Sans'", "system-ui", "-apple-system", "'Segoe UI'", "sans-serif"],
        mono: ["'IBM Plex Mono'", "'JetBrains Mono'", "monospace"],
      },
      fontSize: {
        "overline": ["11px", { lineHeight: "1.4", letterSpacing: "0.04em", fontWeight: "500" }],
        "meta":     ["12px", { lineHeight: "1.4" }],
        "body":     ["13px", { lineHeight: "1.5" }],
        "input":    ["13px", { lineHeight: "1.5" }],
        "panel-title": ["14px", { lineHeight: "1.3", fontWeight: "600" }],
        "page-title":  ["18px", { lineHeight: "1.2", fontWeight: "600" }],
        "stat":     ["24px", { lineHeight: "1", fontWeight: "600" }],
      },
      borderRadius: {
        sm:      "4px",
        DEFAULT: "6px",
        md:      "6px",
        lg:      "6px",
        xl:      "6px",
      },
      boxShadow: {
        drawer: "0 8px 24px rgba(16,24,40,.12)",
        dialog: "0 8px 24px rgba(16,24,40,.12)",
        none:   "none",
      },
      transitionDuration: {
        DEFAULT: "140ms",
        fast: "100ms",
      },
    },
  },
  plugins: [],
}
