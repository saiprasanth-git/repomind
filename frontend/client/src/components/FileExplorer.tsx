/**
 * FileExplorer — left panel sidebar showing the repo file tree.
 * Clicking a file opens it in the code viewer.
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, ChevronDown, FileCode2, Folder, FolderOpen } from 'lucide-react';
import { ScrollArea } from '@/components/ui/scroll-area';
import { reposApi } from '@/lib/api';
import { useRepoStore } from '@/stores/repoStore';
import type { TreeNode } from '@shared/schema';

// Language → color mapping for file icons
const LANG_COLORS: Record<string, string> = {
  Python: 'text-blue-400',
  TypeScript: 'text-blue-300',
  'TypeScript (React)': 'text-blue-300',
  JavaScript: 'text-yellow-300',
  'JavaScript (React)': 'text-yellow-300',
  Java: 'text-orange-400',
  Go: 'text-cyan-400',
  Rust: 'text-orange-300',
  Markdown: 'text-gray-400',
  YAML: 'text-pink-300',
  JSON: 'text-yellow-200',
  SQL: 'text-green-300',
};

interface TreeItemProps {
  name: string;
  node: TreeNode;
  depth: number;
  repoId: string;
}

function TreeItem({ name, node, depth, repoId }: TreeItemProps) {
  const [open, setOpen] = useState(depth < 1);
  const activeFile = useRepoStore(s => s.activeFile);
  const setActiveFile = useRepoStore(s => s.setActiveFile);

  const indent = depth * 12;

  if (node.type === 'file') {
    const colorClass = LANG_COLORS[node.language || ''] || 'text-muted-foreground';
    const isActive = activeFile === node.path;

    return (
      <button
        data-testid={`tree-file-${name}`}
        onClick={() => setActiveFile(node.path!)}
        className={`tree-item w-full text-left ${isActive ? 'active' : ''}`}
        style={{ paddingLeft: `${indent + 8}px` }}
      >
        <FileCode2 size={12} className={`flex-shrink-0 ${colorClass}`} />
        <span className="truncate">{name}</span>
      </button>
    );
  }

  // Directory node
  const children = node.children || (node as any);
  const childEntries = Object.entries(children).filter(([k]) => k !== 'type' && k !== 'children');

  return (
    <div>
      <button
        onClick={() => setOpen(o => !o)}
        className="tree-item w-full text-left"
        style={{ paddingLeft: `${indent + 8}px` }}
      >
        {open
          ? <ChevronDown size={11} className="flex-shrink-0 text-muted-foreground" />
          : <ChevronRight size={11} className="flex-shrink-0 text-muted-foreground" />
        }
        {open
          ? <FolderOpen size={12} className="flex-shrink-0 text-amber-300/70" />
          : <Folder size={12} className="flex-shrink-0 text-amber-300/70" />
        }
        <span className="truncate text-foreground/80">{name}</span>
      </button>
      {open && childEntries.map(([childName, childNode]) => (
        <TreeItem
          key={childName}
          name={childName}
          node={childNode as TreeNode}
          depth={depth + 1}
          repoId={repoId}
        />
      ))}
    </div>
  );
}

interface Props {
  repoId: string;
}

export function FileExplorer({ repoId }: Props) {
  const { data, isLoading } = useQuery({
    queryKey: ['repo-tree', repoId],
    queryFn: () => reposApi.getTree(repoId),
    staleTime: 5 * 60 * 1000,
  });

  return (
    <div className="panel h-full">
      <div className="panel-header">
        <Folder size={11} />
        <span>Explorer</span>
        {data && (
          <span className="ml-auto font-mono normal-case text-muted-foreground/60">
            {data.total_files}
          </span>
        )}
      </div>
      <ScrollArea className="flex-1">
        <div className="py-1">
          {isLoading ? (
            <div className="space-y-1 px-2 py-2">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-5 rounded bg-muted animate-pulse" style={{ width: `${60 + i * 5}%` }} />
              ))}
            </div>
          ) : data?.tree ? (
            Object.entries(data.tree).map(([name, node]) => (
              <TreeItem key={name} name={name} node={node as TreeNode} depth={0} repoId={repoId} />
            ))
          ) : (
            <p className="text-xs text-muted-foreground px-3 py-2">No files found</p>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
