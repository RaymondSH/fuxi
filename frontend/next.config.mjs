/** @type {import('next').NextConfig} */
const BACKEND = process.env.BACKEND_ORIGIN || "http://localhost:8000";

const nextConfig = {
  // 开发期把 /api/* 代理到 FastAPI 后端，前端始终用相对路径 /api 请求
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
