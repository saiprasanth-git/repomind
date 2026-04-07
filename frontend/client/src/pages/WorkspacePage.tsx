/**
 * WorkspacePage — the main 3-panel workspace shown after a repo is indexed.
 * Layout: [File Explorer] [Code Viewer] [Chat Panel]
 */
import { useState } from 'react';
import { useParams, useLocation } from 'wouter';
import { useQuery } from '@tanstack/react-query';
import { RepoHeader } from '@/components/RepoHeader';
import { FileExplorer } from '@/components/FileExplorer';
import { CodeViewer } from '@/components/CodeViewer';
import { ChatPanel } from '@/components/ChatPanel';
import { IngestionProgress } from '@/components/IngestionProgress';
import { Logo } from '@/components/Logo';
import { reposApi } from '@/lib/api';

export default function WorkspacePage() {
  const { id } = useParams<{ id: string }>();
  const [, setLocation] = useLocation();
  const [forceReady, setForceReady] = useState(false);

  const { data: repo, isLoading, error } = useQuery({
    queryKey: ['repo', id],
    queryFn: () => reposApi.get(id!),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'ready' || status === 'failed') return false;
      return 3000;
    },
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="flex items-center gap-3 text-muted-foreground">
          <Logo size={24} className="text-primary animate-pulse" />
          <span className="text-sm">Loading…</span>
        </div>
      </div>
    );
  }

  if (error || !repo) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="text-center space-y-3">
          <p className="text-sm text-muted-foreground">Repository not found</p>
          <button
            onClick={() => setLocation('/')}
            className="text-xs text-primary hover:underline"
          >
            ← Back to home
          </button>
        </div>
      </div>
    );
  }

  // Show ingestion progress while not ready
  const isReady = forceReady || repo.status === 'ready';

  if (!isReady) {
    return (
      <IngestionProgress
        repoId={id!}
        fullName={repo.full_name}
        onReady={() => setForceReady(true)}
        onFailed={(err) => console.error('Ingestion failed:', err)}
      />
    );
  }

  return (
    <div className="app-shell">
      {/* Top header bar — spans full width */}
      <RepoHeader repo={repo} />

      {/* Main 3-panel workspace */}
      <div className="workspace-shell" style={{ gridColumn: '1 / -1' }}>
        {/* Left: File Explorer */}
        <FileExplorer repoId={id!} />

        {/* Center: Code Viewer */}
        <CodeViewer repoId={id!} />

        {/* Right: Chat Panel */}
        <ChatPanel repoId={id!} />
      </div>
    </div>
  );
}
