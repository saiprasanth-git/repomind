/**
 * CodeViewer — center panel showing file contents with syntax highlighting.
 * Uses Monaco Editor (same editor as VS Code) for full syntax highlighting.
 * Highlights lines cited in AI answers.
 */
import { useQuery } from '@tanstack/react-query';
import Editor from '@monaco-editor/react';
import { FileCode2, Copy, Check } from 'lucide-react';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { queryApi } from '@/lib/api';
import { useRepoStore } from '@/stores/repoStore';

// Map our language names to Monaco language IDs
const LANG_TO_MONACO: Record<string, string> = {
  Python: 'python',
  TypeScript: 'typescript',
  'TypeScript (React)': 'typescript',
  JavaScript: 'javascript',
  'JavaScript (React)': 'javascript',
  Java: 'java',
  Go: 'go',
  Rust: 'rust',
  'C++': 'cpp',
  C: 'c',
  'C#': 'csharp',
  Ruby: 'ruby',
  PHP: 'php',
  Markdown: 'markdown',
  YAML: 'yaml',
  JSON: 'json',
  TOML: 'ini',
  SQL: 'sql',
  Shell: 'shell',
  Terraform: 'hcl',
};

interface Props {
  repoId: string;
}

export function CodeViewer({ repoId }: Props) {
  const activeFile = useRepoStore(s => s.activeFile);
  const highlightedLines = useRepoStore(s => s.highlightedLines);
  const [copied, setCopied] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: ['file-content', repoId, activeFile],
    queryFn: () => queryApi.getFileContent(repoId, activeFile!),
    enabled: !!activeFile,
    staleTime: 5 * 60 * 1000,
  });

  const handleCopy = () => {
    if (data?.content) {
      navigator.clipboard.writeText(data.content);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (!activeFile) {
    return (
      <div className="flex-1 flex items-center justify-center bg-background">
        <div className="text-center space-y-2">
          <FileCode2 size={32} className="text-muted-foreground/30 mx-auto" />
          <p className="text-sm text-muted-foreground">Select a file from the explorer</p>
          <p className="text-xs text-muted-foreground/60">or ask a question — cited files open automatically</p>
        </div>
      </div>
    );
  }

  const monacoLang = LANG_TO_MONACO[data?.language || ''] || 'plaintext';
  const filename = activeFile.split('/').pop();

  return (
    <div className="flex-1 flex flex-col bg-background overflow-hidden">
      {/* File tab header */}
      <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-card flex-shrink-0">
        <div className="flex items-center gap-2">
          <FileCode2 size={13} className="text-primary" />
          <span className="text-xs font-mono text-foreground">{filename}</span>
          <span className="text-xs text-muted-foreground font-mono">{activeFile}</span>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className="text-xs text-muted-foreground font-mono">
              {data.total_lines} lines · {data.language}
            </span>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopy}
            className="h-6 w-6 p-0 text-muted-foreground hover:text-foreground"
          >
            {copied ? <Check size={12} className="text-emerald-400" /> : <Copy size={12} />}
          </Button>
        </div>
      </div>

      {/* Code editor */}
      {isLoading ? (
        <div className="flex-1 p-4 space-y-2">
          {Array.from({ length: 20 }).map((_, i) => (
            <Skeleton key={i} className="h-4" style={{ width: `${30 + Math.random() * 60}%` }} />
          ))}
        </div>
      ) : (
        <div className="flex-1 overflow-hidden">
          <Editor
            language={monacoLang}
            value={data?.content || ''}
            theme="vs-dark"
            options={{
              readOnly: true,
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
              lineNumbers: 'on',
              scrollBeyondLastLine: false,
              wordWrap: 'off',
              renderLineHighlight: 'line',
              occurrencesHighlight: 'off',
              selectionHighlight: false,
              overviewRulerLanes: 0,
              hideCursorInOverviewRuler: true,
              scrollbar: {
                vertical: 'visible',
                horizontal: 'visible',
                verticalScrollbarSize: 6,
                horizontalScrollbarSize: 6,
              },
            }}
            onMount={(editor) => {
              // Scroll to highlighted lines when they change
              if (highlightedLines) {
                editor.revealLineInCenter(highlightedLines.start);
              }
            }}
          />
        </div>
      )}
    </div>
  );
}
