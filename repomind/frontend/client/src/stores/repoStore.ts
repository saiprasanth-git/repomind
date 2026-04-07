/**
 * Zustand store — global UI state for the current session.
 * 
 * We keep only UI-level state here (selected repo, active file, panel sizes).
 * Server data (repos list, query results) lives in TanStack Query cache.
 */
import { create } from 'zustand';
import type { Repository } from '@shared/schema';

interface RepoStore {
  // Currently selected repository
  activeRepo: Repository | null;
  setActiveRepo: (repo: Repository | null) => void;

  // Currently viewed file in the code explorer
  activeFile: string | null;
  setActiveFile: (path: string | null) => void;

  // Right panel mode: 'chat' | 'patch'
  rightPanelMode: 'chat' | 'patch';
  setRightPanelMode: (mode: 'chat' | 'patch') => void;

  // Whether the file explorer sidebar is expanded
  explorerOpen: boolean;
  setExplorerOpen: (open: boolean) => void;

  // Highlighted lines in the code viewer (from source citations)
  highlightedLines: { start: number; end: number } | null;
  setHighlightedLines: (lines: { start: number; end: number } | null) => void;
}

export const useRepoStore = create<RepoStore>((set) => ({
  activeRepo: null,
  setActiveRepo: (repo) => set({ activeRepo: repo, activeFile: null }),

  activeFile: null,
  setActiveFile: (path) => set({ activeFile: path }),

  rightPanelMode: 'chat',
  setRightPanelMode: (mode) => set({ rightPanelMode: mode }),

  explorerOpen: true,
  setExplorerOpen: (open) => set({ explorerOpen: open }),

  highlightedLines: null,
  setHighlightedLines: (lines) => set({ highlightedLines: lines }),
}));
