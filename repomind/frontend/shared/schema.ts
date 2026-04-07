// RepoMind shared types — used by both frontend and backend layer
// These mirror the API response shapes from our FastAPI backend

export type RepoStatus = 'pending' | 'cloning' | 'indexing' | 'ready' | 'failed';
export type EngineType = 'rag' | 'long_context' | 'auto';

export interface Repository {
  id: string;
  github_url: string;
  owner: string;
  name: string;
  full_name: string;
  status: RepoStatus;
  error_message: string | null;
  total_files: number;
  indexed_files: number;
  total_chunks: number;
  total_tokens: number;
  repo_size_kb: number;
  description: string | null;
  language: string | null;
  stars: number;
  created_at: string;
  updated_at: string;
  indexed_at: string | null;
}

export interface RepoStatusResponse {
  id: string;
  status: RepoStatus;
  indexed_files: number;
  total_files: number;
  total_chunks: number;
  error_message: string | null;
  progress_percent: number;
}

export interface SourceReference {
  file_path: string;
  start_line: number;
  end_line: number;
  content_preview: string;
  similarity_score: number | null;
}

export interface QueryResponse {
  query_id: string;
  question: string;
  answer: string;
  engine_used: string;
  model: string;
  sources: SourceReference[];
  latency_ms: number;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
  created_at: string;
}

export interface PatchResponse {
  query_id: string;
  description: string;
  patch: string;
  affected_files: string[];
  explanation: string;
  latency_ms: number;
  created_at: string;
}

export interface FileContent {
  file_path: string;
  content: string;
  language: string;
  extension: string;
  total_lines: number;
  chunks: number;
}

export interface TreeNode {
  type: 'file' | 'directory';
  language?: string;
  extension?: string;
  path?: string;
  children?: Record<string, TreeNode>;
}

export interface QueryHistoryItem {
  id: string;
  question: string;
  engine: string;
  latency_ms: number;
  created_at: string;
}
