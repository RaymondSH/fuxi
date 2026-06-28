// 与 docs/api-contract.md 对齐的前端类型定义。

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
