/**
 * Expo 配置（动态部分）。
 * 静态配置在 app.json；这里可注入环境相关的运行时变量。
 * 当前无动态逻辑，保留入口供后续按环境注入配置。
 *
 * EXPO_PUBLIC_API_BASE：后端 API 根路径（在 lib/api.ts 读取）。
 *   默认指向线上前端 :19000 的 /api 反代（复用 Next.js rewrites，等同访问后端）。
 *   本地开发后端时设 EXPO_PUBLIC_API_BASE=http://localhost:8000/api。
 */
import type { ExpoConfig } from "@expo/config-types";

export default ({ config }: { config: ExpoConfig }): ExpoConfig => {
  return config;
};
