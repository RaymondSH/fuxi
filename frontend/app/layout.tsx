import type { Metadata } from "next";
import AuthProvider from "@/components/AuthProvider";
import AppShell from "@/components/AppShell";
import SpacesProvider from "@/components/SpacesProvider";
import "./globals.css";

export const metadata: Metadata = {
  title: "fuxi 知识库",
  description: "个人 AI 知识库 · 入库 / 检索 / 问答 / 知识图谱",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <AuthProvider>
          <SpacesProvider>
            <AppShell>{children}</AppShell>
          </SpacesProvider>
        </AuthProvider>
      </body>
    </html>
  );
}
