"use client";

// 空间上下文：挂载时拉 /spaces（当前用户可见空间），持久化「当前活动空间」到 localStorage。
// 提供 useSpaces() 给全应用读取：
//   - spaces：可见空间列表（含 my_role / member_count）
//   - activeSpace：当前选中的空间（切换后写入 localStorage，刷新仍记住）
//   - setActiveSpace：切换活动空间
//   - reload：成员变更后重新拉取
//
// 设计取舍：后端读接口（检索/笔记/问答/图谱/wiki）按用户可见空间集合过滤，
// 不接受客户端传 space_id（避免越权）。前端「活动空间」主要用于：
//   1. 入库时选择目标空间（POST /ingest/* 带 space_id）
//   2. 空间管理页定位
// 读列表仍返回该用户全部可见空间的内容；活动空间切换只影响入库默认目标。

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { apiGet } from "@/lib/api";
import type { SpaceWithMembership } from "@/lib/types";

const ACTIVE_KEY = "fuxi_active_space";
const DEFAULT_NONE = "__all__"; // 「全部空间」占位（入库时不传 space_id 由后端定默认）

interface SpacesState {
  spaces: SpaceWithMembership[];
  loading: boolean;
  // activeId：当前活动空间 id；DEFAULT_NONE 表示「全部」（不指定）
  activeId: string;
  activeSpace: SpaceWithMembership | null;
  setActiveId: (id: string) => void;
  reload: () => Promise<void>;
}

const SpacesContext = createContext<SpacesState | null>(null);

export function useSpaces(): SpacesState {
  const ctx = useContext(SpacesContext);
  if (!ctx) throw new Error("useSpaces 必须在 SpacesProvider 内使用");
  return ctx;
}

function loadActiveId(): string {
  if (typeof window === "undefined") return DEFAULT_NONE;
  return window.localStorage.getItem(ACTIVE_KEY) || DEFAULT_NONE;
}

function saveActiveId(id: string) {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(ACTIVE_KEY, id);
  }
}

export default function SpacesProvider({ children }: { children: React.ReactNode }) {
  const [spaces, setSpaces] = useState<SpaceWithMembership[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveIdState] = useState<string>(DEFAULT_NONE);

  const reload = useCallback(async () => {
    try {
      const res = await apiGet<{ items: SpaceWithMembership[] }>("/spaces");
      setSpaces(res.items);
      // 记忆的活动空间若已不在可见列表里，回退到「全部」
      const current = loadActiveId();
      if (current !== DEFAULT_NONE && !res.items.some((s) => s.id === current)) {
        setActiveIdState(DEFAULT_NONE);
        saveActiveId(DEFAULT_NONE);
      } else {
        setActiveIdState(current);
      }
    } catch {
      /* 拉取失败静默：未登录时由 AuthProvider 跳转，这里不重复处理 */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const setActiveId = useCallback((id: string) => {
    setActiveIdState(id);
    saveActiveId(id);
  }, []);

  const activeSpace = activeId === DEFAULT_NONE ? null : spaces.find((s) => s.id === activeId) || null;

  return (
    <SpacesContext.Provider
      value={{ spaces, loading, activeId, activeSpace, setActiveId, reload }}
    >
      {children}
    </SpacesContext.Provider>
  );
}

// 角色等级（与后端 _ROLE_LEVEL 对齐），便于前端做 UI 守卫
export const ROLE_LEVEL: Record<string, number> = {
  viewer: 1,
  editor: 2,
  space_admin: 3,
};

export function canAct(activeRole: string | null | undefined, min: string): boolean {
  if (!activeRole) return false;
  return (ROLE_LEVEL[activeRole] || 0) >= (ROLE_LEVEL[min] || 0);
}

// 给入库等接口用的 space_id：活动空间为「全部」时返回 undefined（后端落 default）
export function activeSpaceForIngest(activeId: string): string | undefined {
  return activeId === DEFAULT_NONE ? undefined : activeId;
}
