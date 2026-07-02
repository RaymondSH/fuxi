// 与 docs/api-contract.md 对齐的前端类型定义。

export type UserRole = "member" | "admin";
export type SpaceRole = "viewer" | "editor" | "space_admin";

export interface User {
  id: string;
  username: string | null;
  email: string;
  display_name: string | null;
  role: UserRole;
  daily_token_limit: number | null;
  is_active: boolean;
}

export interface UsageRow {
  id: string;
  email: string;
  display_name: string | null;
  role: UserRole;
  limit: number | null; // null = 不限（admin）
  used_today: number;
}

// GET /auth/usage 组织趋势的一天
export interface UsageTrendPoint {
  day: string; // ISO date
  total: number;
}

// GET /auth/usage 用量告警（今日已达额度 80%）
export interface UsageAlert {
  id: string;
  email: string;
  display_name: string | null;
  used_today: number;
  limit: number;
  pct: number;
}

export interface SystemStatus {
  version: string;
  storage_backend: string; // local | r2
  pg_version: string;
  pgvector_version: string | null;
  notes: number;
  entities: number;
  wikis: number;
  db_size_bytes: number;
  disk: { total_bytes: number; used_bytes: number; free_bytes: number } | null;
}

export type NoteType = "link" | "pdf" | "word" | "excel" | "image";
export type SearchMode = "hybrid" | "keyword" | "semantic";
export type EntityCat = "concept" | "product" | "company";
export type IngestStatus = "pending" | "processing" | "done" | "failed";
export type IngestStage =
  | "queued"
  | "fetch"
  | "extract"
  | "refine"
  | "chunk"
  | "embedding"
  | "store"
  | "done";

export interface EntityRef {
  id: string;
  name: string;
  cat: EntityCat;
}

export interface Note {
  id: string;
  type: NoteType;
  title: string;
  source: string;
  url?: string;
  date: string;
  tags: string[];
  entities: EntityRef[];
  summary: string;
  keypoints: string[];
  original: string[];
  related_note_ids: string[];
  revision?: number;
  authority?: number;
  can_edit?: boolean;
  can_delete?: boolean;
  refresh_policy?: "manual" | "daily" | "weekly";
  source_status?: "active" | "broken" | "disabled";
  space_id: string;
}

// GET /notes/{id}/qa 文档→Q&A 生成产物
export interface GeneratedQaItem {
  question: string;
  answer: string;
}

export interface NoteSummary {
  id: string;
  type: NoteType;
  title: string;
  source: string;
  date: string;
  tags: string[];
  summary: string;
  score?: number;
  snippet?: string;
}

// GET /notes 笔记列表（分页）
export interface NoteListResponse {
  items: NoteSummary[];
  total: number;
  page: number;
  size: number;
}

export interface GraphNode {
  id: string;
  name: string;
  cat: EntityCat;
  count: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: [string, string][];
}

export interface EntityDetail {
  id: string;
  name: string;
  cat: EntityCat;
  count: number;
  aliases: string[];
  notes: { id: string; title: string; type: NoteType; date: string | null }[];
}

export interface WikiSummary {
  slug: string;
  title: string;
  updated: string | null;
  source_count: number;
  space_id?: string | null;
}

export interface WikiParagraph {
  text: string;
  cites: string[];
}

export interface WikiSection {
  heading: string;
  paragraphs: WikiParagraph[];
}

export interface WikiConflict {
  topic: string;
  sides: { note_id: string; claim: string }[];
}

export interface WikiDetail {
  slug: string;
  title: string;
  updated: string | null;
  source_ids: string[];
  sources: { id: string; title: string; type: NoteType }[];
  sections: WikiSection[];
  conflict: WikiConflict | null;
  space_id?: string | null;
}

export interface IngestJob {
  id: string;
  note_id: string;
  type: NoteType;
  title: string;
  sub: string;
  stage: IngestStage;
  progress: number;
  status: IngestStatus;
  error_msg?: string;
}

// MCP API token（仅前缀用于识别，明文只在创建时返回一次）
export interface McpToken {
  id: string;
  name: string;
  prefix: string;
  is_active: boolean;
  space_id: string | null;
  space_name: string | null;
  created_at: string;
  last_used_at: string | null;
}

export interface McpTokenCreated {
  token: string; // 明文，仅本次返回
  token_id: string;
  name: string;
  prefix: string;
  space_id: string | null;
}

// ── 空间（Spaces）── M2 多团队内容隔离

export interface Space {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  is_default: boolean;
  owner_id: string | null;
  created_at: string;
}

// GET /spaces 返回的空间（带当前用户角色 + 成员数）
export interface SpaceWithMembership extends Space {
  my_role: SpaceRole | null; // sysadmin 视角恒为 space_admin
  member_count: number;
}

export interface SpaceMember {
  user_id: string;
  email: string;
  display_name: string | null;
  role: SpaceRole;
  created_at: string;
}

// GET /spaces/{id}/members/search 加成员时选人
export interface UserLookup {
  user_id: string;
  email: string;
  display_name: string | null;
  is_member: boolean;
}
