import { useState } from 'react';
import { useLocation } from 'wouter';
import { useMutation } from '@tanstack/react-query';
import { GitBranch, Zap, Search, Code2, ArrowRight, Star } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Logo } from '@/components/Logo';
import { reposApi } from '@/lib/api';
import { useRepoStore } from '@/stores/repoStore';

const EXAMPLE_REPOS = [
  'https://github.com/fastapi/fastapi',
  'https://github.com/langchain-ai/langchain',
  'https://github.com/tiangolo/sqlmodel',
];

export default function LandingPage() {
  const [, setLocation] = useLocation();
  const [url, setUrl] = useState('');
  const [error, setError] = useState('');
  const setActiveRepo = useRepoStore(s => s.setActiveRepo);

  const ingestMutation = useMutation({
    mutationFn: reposApi.ingest,
    onSuccess: (data) => {
      setLocation(`/repo/${data.id}`);
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail || 'Failed to start indexing. Check the URL and try again.';
      setError(msg);
    },
  });

  const handleSubmit = (repoUrl = url) => {
    setError('');
    if (!repoUrl.trim()) return;
    ingestMutation.mutate(repoUrl.trim());
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">

      {/* Nav */}
      <nav className="flex items-center justify-between px-6 py-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Logo size={28} className="text-primary" />
          <span className="font-semibold text-foreground tracking-tight">RepoMind</span>
        </div>
        <div className="flex items-center gap-3">
          <a
            href="https://github.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            GitHub
          </a>
          <Badge variant="secondary" className="text-xs font-mono">v1.0</Badge>
        </div>
      </nav>

      {/* Hero */}
      <main className="flex-1 flex flex-col items-center justify-center px-4 py-16">

        <div className="max-w-2xl w-full text-center mb-10">
          <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/5 px-3 py-1 text-xs text-primary mb-6">
            <Zap size={11} />
            <span>RAG + Long-Context · Gemini 1.5 Pro · 2M Token Window</span>
          </div>

          <h1 className="text-4xl font-bold tracking-tight text-foreground mb-4 leading-tight">
            Talk to any GitHub repo like a{' '}
            <span className="text-gradient-indigo">senior engineer</span>
          </h1>

          <p className="text-muted-foreground text-base leading-relaxed max-w-lg mx-auto">
            Paste a GitHub URL. Ask questions in plain English. Get answers with exact
            file citations, architecture explanations, and AI-generated patches.
          </p>
        </div>

        {/* URL Input */}
        <div className="w-full max-w-xl space-y-3">
          <div className="flex gap-2">
            <div className="relative flex-1">
              <GitBranch
                size={14}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
              />
              <Input
                data-testid="input-github-url"
                value={url}
                onChange={e => { setUrl(e.target.value); setError(''); }}
                onKeyDown={e => e.key === 'Enter' && handleSubmit()}
                placeholder="https://github.com/owner/repo"
                className="pl-9 font-mono text-sm bg-card border-border focus:border-primary h-11"
              />
            </div>
            <Button
              data-testid="button-analyze"
              onClick={() => handleSubmit()}
              disabled={ingestMutation.isPending || !url.trim()}
              className="h-11 px-5 bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              {ingestMutation.isPending ? (
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 border border-white/30 border-t-white rounded-full animate-spin" />
                  Starting…
                </span>
              ) : (
                <span className="flex items-center gap-1.5">
                  Analyze <ArrowRight size={14} />
                </span>
              )}
            </Button>
          </div>

          {error && (
            <p className="text-xs text-destructive px-1">{error}</p>
          )}

          {/* Example repos */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-muted-foreground">Try:</span>
            {EXAMPLE_REPOS.map(repo => {
              const name = repo.split('/').slice(-2).join('/');
              return (
                <button
                  key={repo}
                  onClick={() => { setUrl(repo); handleSubmit(repo); }}
                  className="text-xs font-mono text-primary/80 hover:text-primary border border-primary/20 hover:border-primary/40 rounded-md px-2 py-0.5 transition-colors bg-primary/5"
                >
                  {name}
                </button>
              );
            })}
          </div>
        </div>

        {/* Feature pills */}
        <div className="mt-16 grid grid-cols-1 sm:grid-cols-3 gap-4 max-w-2xl w-full">
          {[
            { icon: Search, title: 'Smart Retrieval', desc: 'pgvector similarity search finds the right code in milliseconds' },
            { icon: Code2, title: 'Full-Repo Context', desc: 'Gemini 1.5 Pro sees your entire codebase in one 2M token window' },
            { icon: Star, title: 'Patch Generation', desc: 'Generate unified diffs with a plain-English description of the change' },
          ].map(({ icon: Icon, title, desc }) => (
            <div
              key={title}
              className="rounded-lg border border-border bg-card p-4 text-left hover:border-primary/30 transition-colors"
            >
              <div className="w-8 h-8 rounded-md bg-primary/10 flex items-center justify-center mb-3">
                <Icon size={15} className="text-primary" />
              </div>
              <p className="text-sm font-medium text-foreground mb-1">{title}</p>
              <p className="text-xs text-muted-foreground leading-relaxed">{desc}</p>
            </div>
          ))}
        </div>
      </main>

      <footer className="py-4 text-center text-xs text-muted-foreground border-t border-border">
        Built in 48 hours · RAG vs Long-Context Research Experiment Included
      </footer>
    </div>
  );
}
