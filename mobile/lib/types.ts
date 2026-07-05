// 与 docs/api-contract.md 对齐的类型定义。
// 移动端首期仅用 User；其余类型为后续检索/问答/图谱页预留，与 frontend/lib/types.ts 保持一致。

export type UserRole = "member" | "admin";

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
  space_id?: string;
}

export interface SearchHistoryItem {
  id: string;
  q: string;
  mode: string;
  hits: number;
  created_at: string;
}

export interface QaHistoryItem {
  id: string;
  question: string;
  answer_preview: string;
  source_count: number;
  created_at: string;
}

export interface SearchResponse {
  query: string;
  mode: string;
  took_ms: number;
  total: number;
  results: NoteSummary[];
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
