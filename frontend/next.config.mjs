/** @type {import('next').NextConfig} */
const BACKEND = process.env.BACKEND_ORIGIN || "http://localhost:8000";

const nextConfig = {
  // 开发期把 /api/* 代理到 FastAPI 后端，前端始终用相对路径 /api 请求
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${BACKEND}/api/:path*` },
      // MCP 也经前端公开端口转发，后端可继续只监听 127.0.0.1。
      { source: "/mcp", destination: `${BACKEND}/mcp` },
      { source: "/mcp/:path*", destination: `${BACKEND}/mcp/:path*` },
    ];
  },
};

export default nextConfig;
