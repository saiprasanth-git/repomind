/**
 * RepoHeader — top bar shown inside the workspace view.
 * Shows repo name, status, stats, and nav controls.
 */
import { useLocation } from 'wouter';
import { ArrowLeft, Star, GitBranch, FileCode2, Cpu, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';
import { Logo } from '@/components/Logo';
import type { Repository } from '@shared/schema';

interface Props {
  repo: Repository;
}

const STATUS_CONFIG = {
  ready:    { label: 'Ready',    class: 'ready' },
  indexing: { label: 'Indexing', class: 'indexing' },
  cloning:  { label: 'Cloning',  class: 'cloning' },
  failed:   { label: 'Failed',   class: 'failed' },
  pending:  { label: 'Pending',  class: 'pending' },
};

export function RepoHeader({ repo }: Props) {
  const [, setLocation] = useLocation();
  const cfg = STATUS_CONFIG[repo.status] || STATUS_CONFIG.pending;

  const formatNumber = (n: number) =>
    n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);

  return (
    <TooltipProvider>
      <header
        className="flex items-center gap-3 px-4 border-b border-border bg-card"
        style={{ height: 'var(--header-height)', gridColumn: '1 / -1' }}
      >
        {/* Logo + back */}
        <button
          onClick={() => setLocation('/')}
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <Logo size={20} className="text-primary" />
        </button>

        <ChevronRight size={12} className="text-muted-foreground/40" />

        {/* Repo identity */}
        <div className="flex items-center gap-2 min-w-0">
          <GitBranch size={13} className="text-muted-foreground flex-shrink-0" />
          <a
            href={repo.github_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm font-medium text-foreground hover:text-primary transition-colors truncate font-mono"
          >
            {repo.full_name}
          </a>
          <div className="flex items-center gap-1 flex-shrink-0">
            <span className={`status-dot ${cfg.class}`} />
            <span className="text-xs text-muted-foreground">{cfg.label}</span>
          </div>
        </div>

        {/* Stats */}
        <div className="hidden md:flex items-center gap-4 ml-4 text-xs text-muted-foreground">
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="flex items-center gap-1 cursor-default">
                <FileCode2 size={11} />
                {formatNumber(repo.total_files)} files
              </span>
            </TooltipTrigger>
            <TooltipContent>{repo.total_files.toLocaleString()} indexed files</TooltipContent>
          </Tooltip>

          <Tooltip>
            <TooltipTrigger asChild>
              <span className="flex items-center gap-1 cursor-default">
                <Cpu size={11} />
                {formatNumber(repo.total_chunks)} chunks
              </span>
            </TooltipTrigger>
            <TooltipContent>
              {repo.total_chunks.toLocaleString()} chunks · ~{formatNumber(repo.total_tokens)} tokens
            </TooltipContent>
          </Tooltip>

          {repo.stars > 0 && (
            <span className="flex items-center gap-1">
              <Star size={11} />
              {formatNumber(repo.stars)}
            </span>
          )}

          {repo.language && (
            <Badge variant="secondary" className="text-xs h-4 px-1.5">
              {repo.language}
            </Badge>
          )}
        </div>

        {/* Right side */}
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setLocation('/')}
            className="h-7 text-xs text-muted-foreground hover:text-foreground gap-1"
          >
            <ArrowLeft size={12} />
            All repos
          </Button>
        </div>
      </header>
    </TooltipProvider>
  );
}
