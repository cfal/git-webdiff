import React from 'react';
import { apiUrl } from './api-utils';

interface FileInfo {
  path: string;
  status?: string;
  is_dir?: boolean;
  file_count?: number;
}

interface FilesResponse {
  changed: FileInfo[];
  untracked: FileInfo[];
  gitignored: FileInfo[];
}

interface FileContentResponse {
  content: string | null;
  is_binary: boolean;
  size: number;
  path: string;
  truncated?: boolean;
  error?: string;
}

interface FileBrowserProps {
  repoIdx: number;
  repoLabel: string;
  onScrollToFile: (path: string) => void;
}

// localStorage key for filter preferences
const STORAGE_KEY_PREFIX = 'webdiff-file-filters-';

interface FilterPreferences {
  showChanged: boolean;
  showUntracked: boolean;
  showGitignored: boolean;
}

const DEFAULT_PREFERENCES: FilterPreferences = {
  showChanged: true,
  showUntracked: false,  // Default unchecked
  showGitignored: false, // Default unchecked
};

function getFilterPreferences(repoLabel: string): FilterPreferences {
  try {
    const stored = localStorage.getItem(STORAGE_KEY_PREFIX + repoLabel);
    if (stored) {
      const parsed = JSON.parse(stored);
      return { ...DEFAULT_PREFERENCES, ...parsed };
    }
  } catch (e) {
    console.error('Failed to load filter preferences:', e);
  }
  return DEFAULT_PREFERENCES;
}

function saveFilterPreferences(repoLabel: string, prefs: FilterPreferences): void {
  try {
    localStorage.setItem(STORAGE_KEY_PREFIX + repoLabel, JSON.stringify(prefs));
  } catch (e) {
    console.error('Failed to save filter preferences:', e);
  }
}

const MONO_FONT = '"JetBrains Mono", Consolas, "Liberation Mono", Menlo, Courier, monospace';
const UI_FONT = 'Arial, sans-serif';

// Status colors matching the mockup
const STATUS_COLORS = {
  modified: '#0366d6',  // Blue
  staged: '#28a745',    // Green
  added: '#28a745',     // Green
  deleted: '#cb2431',   // Red
  untracked: '#f66a0a', // Orange
  ignored: '#6a737d',   // Gray
};

function FileContentModal({
  file,
  repoIdx,
  onClose,
}: {
  file: { path: string; type: 'untracked' | 'gitignored' } | null;
  repoIdx: number;
  onClose: () => void;
}) {
  const [content, setContent] = React.useState<FileContentResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const modalRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    if (!file) return;

    const fetchContent = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await fetch(
          apiUrl(`/api/file-content/${repoIdx}?path=${encodeURIComponent(file.path)}`)
        );
        if (!response.ok) {
          throw new Error('Failed to fetch file content');
        }
        const data = await response.json();
        setContent(data);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Unknown error');
      } finally {
        setLoading(false);
      }
    };

    fetchContent();
  }, [file, repoIdx]);

  // Handle escape key
  React.useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [onClose]);

  // Handle click outside
  const handleBackdropClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!file) return null;

  return (
    <div
      onClick={handleBackdropClick}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0, 0, 0, 0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
    >
      <div
        ref={modalRef}
        style={{
          background: 'white',
          borderRadius: '8px',
          boxShadow: '0 4px 24px rgba(0, 0, 0, 0.2)',
          maxWidth: '900px',
          width: '90%',
          maxHeight: '80vh',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '12px 16px',
            borderBottom: '1px solid #e1e4e8',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: '#f6f8fa',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <code
              style={{
                fontFamily: MONO_FONT,
                fontSize: '14px',
                color: '#24292e',
              }}
            >
              {file.path}
            </code>
            <span
              style={{
                fontSize: '12px',
                color: file.type === 'untracked' ? STATUS_COLORS.untracked : STATUS_COLORS.ignored,
                background: file.type === 'untracked' ? '#fff8f0' : '#f6f8fa',
                padding: '2px 8px',
                borderRadius: '3px',
              }}
            >
              {file.type === 'untracked' ? 'Untracked' : 'Gitignored'}
            </span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'none',
              border: 'none',
              fontSize: '20px',
              cursor: 'pointer',
              color: '#586069',
              padding: '4px 8px',
            }}
          >
            ×
          </button>
        </div>

        {/* Content */}
        <div
          style={{
            flex: 1,
            overflow: 'auto',
            padding: '0',
          }}
        >
          {loading && (
            <div
              style={{
                padding: '40px',
                textAlign: 'center',
                color: '#6a737d',
                fontFamily: UI_FONT,
              }}
            >
              Loading...
            </div>
          )}

          {error && (
            <div
              style={{
                padding: '20px',
                color: '#cb2431',
                background: '#ffeef0',
                fontFamily: UI_FONT,
              }}
            >
              Error: {error}
            </div>
          )}

          {content && content.is_binary && (
            <div
              style={{
                padding: '40px',
                textAlign: 'center',
                color: '#6a737d',
                fontFamily: UI_FONT,
              }}
            >
              Binary file ({formatBytes(content.size)})
            </div>
          )}

          {content && content.truncated && (
            <div
              style={{
                padding: '40px',
                textAlign: 'center',
                color: '#6a737d',
                fontFamily: UI_FONT,
              }}
            >
              File too large to display ({formatBytes(content.size)})
            </div>
          )}

          {content && content.content && (
            <pre
              style={{
                margin: 0,
                padding: '12px',
                fontFamily: MONO_FONT,
                fontSize: '13px',
                lineHeight: '1.5',
                overflow: 'auto',
                background: '#fafbfc',
              }}
            >
              {content.content.split('\n').map((line, idx) => (
                <div key={idx} style={{ display: 'flex' }}>
                  <span
                    style={{
                      color: '#6a737d',
                      paddingRight: '16px',
                      textAlign: 'right',
                      minWidth: '40px',
                      userSelect: 'none',
                    }}
                  >
                    {idx + 1}
                  </span>
                  <span style={{ flex: 1 }}>{line || ' '}</span>
                </div>
              ))}
            </pre>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 16px',
            borderTop: '1px solid #e1e4e8',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '8px',
            background: '#f6f8fa',
          }}
        >
          <button
            onClick={() => {
              navigator.clipboard.writeText(file.path);
            }}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontFamily: UI_FONT,
              background: '#fafbfc',
              border: '1px solid #d1d5da',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Copy path
          </button>
          <button
            onClick={onClose}
            style={{
              padding: '6px 12px',
              fontSize: '13px',
              fontFamily: UI_FONT,
              background: '#0366d6',
              color: 'white',
              border: 'none',
              borderRadius: '4px',
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function FileBrowser({ repoIdx, repoLabel, onScrollToFile }: FileBrowserProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [files, setFiles] = React.useState<FilesResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  // Load initial filter preferences from localStorage
  const initialPrefs = React.useMemo(() => getFilterPreferences(repoLabel), [repoLabel]);

  // Filter state - initialized from localStorage with new defaults
  const [showChanged, setShowChanged] = React.useState(initialPrefs.showChanged);
  const [showUntracked, setShowUntracked] = React.useState(initialPrefs.showUntracked);
  const [showGitignored, setShowGitignored] = React.useState(initialPrefs.showGitignored);

  // Save preferences when they change
  React.useEffect(() => {
    saveFilterPreferences(repoLabel, { showChanged, showUntracked, showGitignored });
  }, [repoLabel, showChanged, showUntracked, showGitignored]);

  // Modal state
  const [selectedFile, setSelectedFile] = React.useState<{
    path: string;
    type: 'untracked' | 'gitignored';
  } | null>(null);

  const fetchFiles = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl(`/api/files/${repoIdx}`));
      if (!response.ok) {
        throw new Error('Failed to fetch files');
      }
      const data = await response.json();
      setFiles(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [repoIdx]);

  React.useEffect(() => {
    if (isExpanded && !files) {
      fetchFiles();
    }
  }, [isExpanded, files, fetchFiles]);

  const handleFileClick = (file: FileInfo, type: 'changed' | 'untracked' | 'gitignored') => {
    if (type === 'changed') {
      // Scroll to the diff for this file
      onScrollToFile(file.path);
    } else {
      // Open modal for untracked/gitignored files
      setSelectedFile({ path: file.path, type });
    }
  };

  // Compute counts for header
  const changedCount = files?.changed.length ?? 0;
  const untrackedCount = files?.untracked.length ?? 0;
  const gitignoredCount = files?.gitignored.length ?? 0;

  return (
    <>
      <div
        style={{
          background: '#fafbfc',
          border: '1px solid #d1d5da',
          borderRadius: '6px',
          marginBottom: '8px',
          overflow: 'hidden',
        }}
      >
        {/* Header - always visible */}
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          style={{
            width: '100%',
            padding: '10px 12px',
            background: isExpanded ? '#f1f3f5' : '#fafbfc',
            border: 'none',
            borderBottom: isExpanded ? '1px solid #d1d5da' : 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '14px',
            fontFamily: UI_FONT,
            fontWeight: 600,
            color: '#24292e',
            textAlign: 'left',
          }}
        >
          <span
            style={{
              transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
              transition: 'transform 0.15s',
              display: 'inline-block',
            }}
          >
            ▶
          </span>
          <span>Files</span>
          {files && (
            <span
              style={{
                color: '#6a737d',
                fontWeight: 400,
                fontSize: '13px',
              }}
            >
              {changedCount > 0 && (
                <span style={{ color: STATUS_COLORS.modified }}>
                  {changedCount} changed
                </span>
              )}
              {changedCount > 0 && untrackedCount > 0 && ' · '}
              {untrackedCount > 0 && (
                <span style={{ color: STATUS_COLORS.untracked }}>
                  {untrackedCount} untracked
                </span>
              )}
              {(changedCount > 0 || untrackedCount > 0) && gitignoredCount > 0 && ' · '}
              {gitignoredCount > 0 && (
                <span style={{ color: STATUS_COLORS.ignored }}>
                  {gitignoredCount} ignored
                </span>
              )}
            </span>
          )}
        </button>

        {/* File list - collapsible */}
        {isExpanded && (
          <div style={{ maxHeight: '500px', overflowY: 'auto' }}>
            {error && (
              <div
                style={{
                  padding: '12px',
                  color: '#cb2431',
                  background: '#ffeef0',
                  fontSize: '13px',
                  fontFamily: UI_FONT,
                }}
              >
                Error: {error}
              </div>
            )}

            {/* Filters */}
            <div
              style={{
                padding: '8px 12px',
                borderBottom: '1px solid #eaecef',
                display: 'flex',
                gap: '16px',
                fontSize: '13px',
                fontFamily: UI_FONT,
              }}
            >
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showChanged}
                  onChange={(e) => setShowChanged(e.target.checked)}
                />
                <span style={{ color: STATUS_COLORS.modified }}>Changed</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showUntracked}
                  onChange={(e) => setShowUntracked(e.target.checked)}
                />
                <span style={{ color: STATUS_COLORS.untracked }}>Untracked</span>
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: '4px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={showGitignored}
                  onChange={(e) => setShowGitignored(e.target.checked)}
                />
                <span style={{ color: STATUS_COLORS.ignored }}>Gitignored</span>
              </label>
            </div>

            {/* Changed files */}
            {showChanged && files && files.changed.length > 0 && (
              <FileSection
                title="CHANGED"
                files={files.changed}
                type="changed"
                onFileClick={handleFileClick}
              />
            )}

            {/* Untracked files */}
            {showUntracked && files && files.untracked.length > 0 && (
              <FileSection
                title="UNTRACKED"
                files={files.untracked}
                type="untracked"
                onFileClick={handleFileClick}
              />
            )}

            {/* Gitignored files */}
            {showGitignored && files && files.gitignored.length > 0 && (
              <FileSection
                title="GITIGNORED"
                files={files.gitignored}
                type="gitignored"
                onFileClick={handleFileClick}
              />
            )}

            {/* Loading state */}
            {loading && (
              <div
                style={{
                  padding: '20px',
                  textAlign: 'center',
                  color: '#6a737d',
                  fontSize: '13px',
                  fontFamily: UI_FONT,
                }}
              >
                Loading files...
              </div>
            )}

            {/* Empty state */}
            {!loading && files && changedCount === 0 && untrackedCount === 0 && gitignoredCount === 0 && (
              <div
                style={{
                  padding: '20px',
                  textAlign: 'center',
                  color: '#6a737d',
                  fontSize: '13px',
                  fontFamily: UI_FONT,
                }}
              >
                No files found
              </div>
            )}
          </div>
        )}
      </div>

      {/* File content modal */}
      {selectedFile && (
        <FileContentModal file={selectedFile} repoIdx={repoIdx} onClose={() => setSelectedFile(null)} />
      )}
    </>
  );
}

function FileSection({
  title,
  files,
  type,
  onFileClick,
}: {
  title: string;
  files: FileInfo[];
  type: 'changed' | 'untracked' | 'gitignored';
  onFileClick: (file: FileInfo, type: 'changed' | 'untracked' | 'gitignored') => void;
}) {
  const getStatusColor = (file: FileInfo) => {
    if (type === 'untracked') return STATUS_COLORS.untracked;
    if (type === 'gitignored') return STATUS_COLORS.ignored;
    if (file.status === 'added') return STATUS_COLORS.added;
    if (file.status === 'deleted') return STATUS_COLORS.deleted;
    return STATUS_COLORS.modified;
  };

  const getStatusLabel = (file: FileInfo) => {
    if (type === 'untracked') return 'New file';
    if (type === 'gitignored') return 'Ignored';
    if (file.status === 'added') return 'Added';
    if (file.status === 'deleted') return 'Deleted';
    return 'Modified';
  };

  const getIcon = (file: FileInfo) => {
    if (type === 'gitignored') return '◌';
    if (type === 'untracked') return '○';
    return '●';
  };

  return (
    <div style={{ padding: '8px 0' }}>
      <div
        style={{
          padding: '4px 12px',
          fontSize: '11px',
          fontWeight: 600,
          color: '#6a737d',
          fontFamily: UI_FONT,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
        }}
      >
        {title}
      </div>
      {files.map((file, idx) => (
        <div
          key={`${file.path}-${idx}`}
          onClick={() => !file.is_dir && onFileClick(file, type)}
          style={{
            padding: '6px 12px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            cursor: file.is_dir ? 'default' : 'pointer',
            transition: 'background 0.1s',
          }}
          onMouseEnter={(e) => {
            if (!file.is_dir) {
              e.currentTarget.style.background = '#f6f8fa';
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.background = 'transparent';
          }}
        >
          <span
            style={{
              color: getStatusColor(file),
              fontSize: '10px',
            }}
          >
            {getIcon(file)}
          </span>
          <code
            style={{
              fontFamily: MONO_FONT,
              fontSize: '13px',
              color: '#24292e',
              flex: 1,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {file.path}
          </code>
          <span
            style={{
              fontSize: '12px',
              color: getStatusColor(file),
              whiteSpace: 'nowrap',
            }}
          >
            {file.is_dir ? `${file.file_count} files` : getStatusLabel(file)}
          </span>
        </div>
      ))}
    </div>
  );
}
