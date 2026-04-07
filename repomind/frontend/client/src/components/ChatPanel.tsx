/**
 * ChatPanel — right panel for asking questions about the repo.
 * Shows conversation history, engine selector, and source citations.
 */
import { useState, useRef, useEffect } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Send, Zap, Brain, ChevronDown, FileCode2, Clock, DollarSign } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { queryApi } from '@/lib/api';
import { useRepoStore } from '@/stores/repoStore';
import type { EngineType, QueryResponse, SourceReference } from '@shared/schema';

// Install react-markdown if needed
// This renders markdown in AI answers (code blocks, bold, etc.)

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: SourceReference[];
  engine?: string;
  latency_ms?: number;
  cost?: number;
}

const ENGINE_LABELS: Record<EngineType, { label: string; icon: typeof Zap; desc: string }> = {
  auto:         { label: 'Auto', icon: Brain, desc: 'Smart routing based on repo size' },
  rag:          { label: 'RAG', icon: Zap, desc: 'Fast retrieval — best for targeted questions' },
  long_context: { label: 'Full Context', icon: Brain, desc: 'Entire codebase — best for architecture' },
};

interface Props {
  repoId: string;
}

export function ChatPanel({ repoId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [engine, setEngine] = useState<EngineType>('auto');
  const bottomRef = useRef<HTMLDivElement>(null);
  const setActiveFile = useRepoStore(s => s.setActiveFile);
  const setHighlightedLines = useRepoStore(s => s.setHighlightedLines);

  const queryMutation = useMutation({
    mutationFn: ({ question, eng }: { question: string; eng: EngineType }) =>
      queryApi.query(repoId, question, eng),
    onSuccess: (data: QueryResponse) => {
      const msg: Message = {
        id: data.query_id,
        role: 'assistant',
        content: data.answer,
        sources: data.sources,
        engine: data.engine_used,
        latency_ms: data.latency_ms,
        cost: data.estimated_cost_usd,
      };
      setMessages(prev => [...prev, msg]);
    },
    onError: (err: any) => {
      const errMsg = err?.response?.data?.detail || 'Something went wrong. Try again.';
      setMessages(prev => [...prev, {
        id: Date.now().toString(),
        role: 'assistant',
        content: `❌ ${errMsg}`,
      }]);
    },
  });

  const handleSend = () => {
    const q = input.trim();
    if (!q || queryMutation.isPending) return;

    setMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'user',
      content: q,
    }]);
    setInput('');
    queryMutation.mutate({ question: q, eng: engine });
  };

  // Auto-scroll on new message
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, queryMutation.isPending]);

  const handleSourceClick = (source: SourceReference) => {
    setActiveFile(source.file_path);
    if (source.start_line > 0) {
      setHighlightedLines({ start: source.start_line, end: source.end_line });
    }
  };

  const EngineIcon = ENGINE_LABELS[engine].icon;

  const SUGGESTION_QUESTIONS = [
    'Give me an overview of this codebase',
    'Where is the authentication logic?',
    'How does the data flow through this system?',
    'What are the main entry points?',
  ];

  return (
    <div className="panel h-full flex flex-col">
      {/* Header */}
      <div className="panel-header flex-shrink-0">
        <Brain size={11} />
        <span>Chat</span>
        <div className="ml-auto">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="sm" className="h-5 px-2 text-xs gap-1 text-muted-foreground hover:text-foreground">
                <EngineIcon size={10} />
                {ENGINE_LABELS[engine].label}
                <ChevronDown size={9} />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-52">
              <DropdownMenuRadioGroup value={engine} onValueChange={v => setEngine(v as EngineType)}>
                {(Object.entries(ENGINE_LABELS) as [EngineType, typeof ENGINE_LABELS[EngineType]][]).map(([key, val]) => (
                  <DropdownMenuRadioItem key={key} value={key} className="text-xs">
                    <div>
                      <div className="font-medium">{val.label}</div>
                      <div className="text-muted-foreground font-normal">{val.desc}</div>
                    </div>
                  </DropdownMenuRadioItem>
                ))}
              </DropdownMenuRadioGroup>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 px-3 py-3">
        {messages.length === 0 ? (
          <div className="space-y-3">
            <p className="text-xs text-muted-foreground text-center py-4">
              Ask anything about this repository
            </p>
            <div className="space-y-1.5">
              {SUGGESTION_QUESTIONS.map(q => (
                <button
                  key={q}
                  onClick={() => { setInput(q); }}
                  className="w-full text-left text-xs rounded-lg border border-border bg-card/50 px-3 py-2 text-muted-foreground hover:text-foreground hover:border-primary/30 transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map(msg => (
              <div key={msg.id}>
                {msg.role === 'user' ? (
                  <div className="message-user">{msg.content}</div>
                ) : (
                  <div className="space-y-2">
                    <div className="message-ai">
                      <div className="prose prose-sm prose-invert max-w-none text-foreground
                        [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono
                        [&_pre]:bg-muted [&_pre]:p-3 [&_pre]:rounded-lg [&_pre]:overflow-auto [&_pre]:text-xs
                        [&_p]:mb-2 [&_p:last-child]:mb-0
                        [&_ul]:list-disc [&_ul]:pl-4 [&_ul]:mb-2
                        [&_strong]:text-foreground">
                        {msg.content.startsWith('❌') ? (
                          <p className="text-destructive">{msg.content}</p>
                        ) : (
                          <ReactMarkdownSafe content={msg.content} />
                        )}
                      </div>
                    </div>

                    {/* Source citations */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-xs text-muted-foreground px-1">Sources</p>
                        <div className="flex flex-wrap gap-1 px-1">
                          {msg.sources.map((src, i) => (
                            <button
                              key={i}
                              onClick={() => handleSourceClick(src)}
                              className="source-pill"
                            >
                              <FileCode2 size={10} />
                              <span className="truncate max-w-[180px]">
                                {src.file_path.split('/').pop()}
                              </span>
                              {src.start_line > 0 && (
                                <span className="opacity-60">:{src.start_line}</span>
                              )}
                              {src.similarity_score && src.similarity_score > 0 && (
                                <span className="opacity-60 ml-1">{(src.similarity_score * 100).toFixed(0)}%</span>
                              )}
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Metadata */}
                    {msg.latency_ms && (
                      <div className="flex items-center gap-3 px-1">
                        <span className="flex items-center gap-1 text-xs text-muted-foreground/60">
                          <Clock size={9} />
                          {msg.latency_ms < 1000
                            ? `${msg.latency_ms.toFixed(0)}ms`
                            : `${(msg.latency_ms / 1000).toFixed(1)}s`}
                        </span>
                        <Badge variant="secondary" className="text-xs h-4 px-1.5 font-mono">
                          {msg.engine}
                        </Badge>
                        {msg.cost && msg.cost > 0 && (
                          <span className="flex items-center gap-1 text-xs text-muted-foreground/60">
                            <DollarSign size={9} />
                            {msg.cost < 0.01 ? `<$0.01` : `$${msg.cost.toFixed(3)}`}
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Typing indicator */}
            {queryMutation.isPending && (
              <div className="message-ai">
                <div className="flex items-center gap-1.5">
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                  <span className="typing-dot" />
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>
        )}
      </ScrollArea>

      {/* Input */}
      <div className="flex-shrink-0 p-3 border-t border-border">
        <div className="flex gap-2">
          <Textarea
            data-testid="input-question"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Ask about this codebase…"
            className="min-h-0 h-10 py-2.5 resize-none text-sm bg-muted border-border focus:border-primary text-foreground placeholder:text-muted-foreground"
            rows={1}
          />
          <Button
            data-testid="button-send"
            onClick={handleSend}
            disabled={queryMutation.isPending || !input.trim()}
            size="sm"
            className="h-10 w-10 p-0 bg-primary hover:bg-primary/90 flex-shrink-0"
          >
            <Send size={14} />
          </Button>
        </div>
        <p className="text-xs text-muted-foreground/50 mt-1.5 text-right">
          ↵ Send · Shift+↵ New line
        </p>
      </div>
    </div>
  );
}

// Safe markdown renderer that handles missing module gracefully
function ReactMarkdownSafe({ content }: { content: string }) {
  try {
    const ReactMarkdown = require('react-markdown').default;
    return <ReactMarkdown>{content}</ReactMarkdown>;
  } catch {
    // Fallback: render as pre-formatted text
    return <pre className="whitespace-pre-wrap font-sans text-sm">{content}</pre>;
  }
}
