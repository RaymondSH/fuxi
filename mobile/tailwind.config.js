/** NativeWind 色板，对齐 frontend/app/globals.css 的 @theme token。
 *  让 mobile 能用和 Web 一致的 class 名：bg-cream / text-ink / border-line 等。 */
module.exports = {
  // NativeWind v4 必需：注入 RN 适配层，让 Tailwind 生成可用样式
  presets: [require("nativewind/preset")],
  content: ["./app/**/*.{tsx,ts}", "./contexts/**/*.{tsx,ts}", "./components/**/*.{tsx,ts}"],
  theme: {
    extend: {
      colors: {
        brand: "#b25b3c",
        "brand-soft": "#f5e7de",
        cream: "#fbf1e9",
        panel: "#f4f0e8",
        ink: "#2b2722",
        muted: "#6f675b",
        muted2: "#8c8273",
        accent: "#9a4a2f",
        line: "#e7ddd0",
        // 实体类别色
        "cat-concept": "#6e8b5e",
        "cat-concept-soft": "#e9efe2",
        "cat-product": "#b25b3c",
        "cat-product-soft": "#f5e7de",
        "cat-company": "#5c7796",
        "cat-company-soft": "#e4eaf1",
      },
      fontFamily: {
        serif: ['Georgia', "Songti SC", "Noto Serif SC", "serif"],
        mono: ["ui-monospace", "SF Mono", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
