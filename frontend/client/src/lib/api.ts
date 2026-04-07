/**
 * API client — all calls to the RepoMind FastAPI backend go through here.
 * Uses axios with a base URL pointing to the backend.
 */
import axios from 'axios';
import type {
  Repository,
  RepoStatusResponse,
  QueryResponse,
  PatchResponse,
  FileContent,
  QueryHistoryItem,
  EngineType,
} from '@shared/schema';

// In dev: backend runs on port 8000
// In production: same origin (nginx/Cloud Run proxies /api to the backend)
const BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

const api = axios.create({
  baseURL: BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  timeout: 120_000, // 2 min — long-context queries can take a while
});

// ── Repository endpoints ───────────────────────────────────────────────────

export const reposApi = {
  list: () =>
    api.get<{ repos: Repository[]; total: number }>('/repos').then(r => r.data),

  ingest: (github_url: string) =>
    api.post<RepoStatusResponse>('/repos', { github_url }).then(r => r.data),

  get: (id: string) =>
    api.get<Repository>(`/repos/${id}`).then(r => r.data),

  getStatus: (id: string) =>
    api.get<RepoStatusResponse>(`/repos/${id}/status`).then(r => r.data),

  getTree: (id: string) =>
    api.get<{ tree: Record<string, any>; total_files: number }>(`/repos/${id}/tree`).then(r => r.data),

  delete: (id: string) =>
    api.delete(`/repos/${id}`).then(r => r.data),
};

// ── Query endpoints ────────────────────────────────────────────────────────

export const queryApi = {
  query: (repo_id: string, question: string, engine: EngineType = 'auto') =>
    api.post<QueryResponse>(`/repos/${repo_id}/query`, { question, engine }).then(r => r.data),

  patch: (repo_id: string, description: string, target_file?: string) =>
    api.post<PatchResponse>(`/repos/${repo_id}/patch`, { description, target_file }).then(r => r.data),

  getHistory: (repo_id: string) =>
    api.get<{ queries: QueryHistoryItem[] }>(`/repos/${repo_id}/queries`).then(r => r.data),

  getFileContent: (repo_id: string, file_path: string) =>
    api.get<FileContent>(`/repos/${repo_id}/file-content`, {
      params: { file_path },
    }).then(r => r.data),
};
