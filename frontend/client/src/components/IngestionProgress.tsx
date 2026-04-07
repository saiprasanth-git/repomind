/**
 * IngestionProgress — shown while a repo is being cloned/indexed.
 * Polls /repos/{id}/status every 2 seconds and updates the progress bar.
 */
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { GitBranch, Database, Cpu, CheckCircle2, XCircle } from 'lucide-react';
import { Progress } from '@/components/ui/progress';
import { Logo } from '@/components/Logo';
import { reposApi } from '@/lib/api';
import type { RepoStatus } from '@shared/schema';

interface Props {
  repoId: string;
  fullName: string;
  onReady: () => void;
  onFailed: (error: string) => void;
}

const STEPS: { status: RepoStatus[]; icon: typeof GitBranch; label: string }[] = [
  { status: ['cloning'], icon: GitBranch, label: 'Cloning repository' },
  { status: ['indexing'], icon: Database, label: 'Parsing & chunking files' },
  { status: ['indexing'], icon: Cpu, label: 'Generating embeddings' },
  { status: ['ready'], icon: CheckCircle2, label: 'Ready' },
];

export function IngestionProgress({ repoId, fullName, onReady, onFailed }: Props) {
  const { data } = useQuery({
    queryKey: ['repo-status', repoId],
    queryFn: () => reposApi.getStatus(repoId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === 'ready' || status === 'failed') return false;
      return 2000; // poll every 2s while in progress
    },
  });

  useEffect(() => {
    if (data?.status === 'ready') onReady();
    if (data?.status === 'failed') onFailed(data.error_message || 'Unknown error');
  }, [data?.status]);

  const progress = data?.progress_percent ?? 0;
  const status = data?.status ?? 'pending';

  const getStepState = (stepIdx: number) => {
    if (status === 'cloning') return stepIdx === 0 ? 'active' : stepIdx < 0 ? 'done' : 'pending';
    if (status === 'indexing') {
      if (stepIdx === 0) return 'done';
      if (stepIdx === 1 || stepIdx === 2) return 'active';
      return 'pending';
    }
    if (status === 'ready') return 'done';
    return 'pending';
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-md text-center space-y-8">

        {/* Logo pulse animation */}
        <div className="flex justify-center">
          <div className="relative">
            <div className="absolute inset-0 rounded-full bg-primary/20 animate-ping" style={{ margin: '-8px' }} />
            <Logo size={48} className="text-primary relative z-10" />
          </div>
        </div>

        <div>
          <h2 className="text-lg font-semibold text-foreground mb-1">Indexing repository</h2>
          <p className="text-sm font-mono text-primary">{fullName}</p>
          <p className="text-xs text-muted-foreground mt-1">
            This takes 1–3 minutes depending on repo size
          </p>
        </div>

        {/* Progress bar */}
        <div className="space-y-2">
          <Progress value={progress} className="h-1.5" />
          <div className="flex justify-between text-xs text-muted-foreground font-mono">
            <span>{data?.indexed_files ?? 0} / {data?.total_files ?? '?'} files</span>
            <span>{progress.toFixed(0)}%</span>
          </div>
        </div>

        {/* Step indicators */}
        <div className="space-y-3 text-left">
          {STEPS.map(({ icon: Icon, label }, idx) => {
            const state = getStepState(idx);
            return (
              <div key={label} className="flex items-center gap-3">
                <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 transition-colors ${
                  state === 'done'   ? 'bg-emerald-500/20 text-emerald-400' :
                  state === 'active' ? 'bg-primary/20 text-primary' :
                  'bg-muted text-muted-foreground'
                }`}>
                  <Icon size={12} className={state === 'active' ? 'animate-pulse' : ''} />
                </div>
                <span className={`text-sm transition-colors ${
                  state === 'done'   ? 'text-muted-foreground line-through' :
                  state === 'active' ? 'text-foreground font-medium' :
                  'text-muted-foreground'
                }`}>
                  {label}
                </span>
                {state === 'active' && (
                  <div className="flex gap-1 ml-auto">
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                    <span className="typing-dot" />
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {status === 'failed' && (
          <div className="flex items-center gap-2 rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive">
            <XCircle size={14} />
            <span>{data?.error_message || 'Indexing failed. Please try again.'}</span>
          </div>
        )}
      </div>
    </div>
  );
}
