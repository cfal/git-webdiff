import React from 'react';
import { apiUrl } from './api-utils';

interface Commit {
  hash: string;
  short_hash: string;
  message: string;
  author: string;
  date: string;
  relative: string;
}

interface CommitHistoryProps {
  repoIdx: number;
  onSelectCommit: (hash: string) => void;
  onSelectWorkingChanges: () => void;
  reloadInProgress: boolean;
  currentGitArgs: string[];
}

const MONO_FONT = '"JetBrains Mono", Consolas, "Liberation Mono", Menlo, Courier, monospace';
const UI_FONT = 'Arial, sans-serif';

// Parse git args to extract selected commit hash
// Format: "{hash}^..{hash}" means viewing that specific commit
function parseSelectedCommit(gitArgs: string[]): string | null {
  if (gitArgs.length === 0) return null; // Working changes
  const arg = gitArgs[0];
  // Match pattern like "abc1234^..abc1234"
  const match = arg.match(/^([a-f0-9]+)\^\.\.([a-f0-9]+)$/i);
  if (match && match[1] === match[2]) {
    return match[1];
  }
  return null;
}

export function CommitHistory({
  repoIdx,
  onSelectCommit,
  onSelectWorkingChanges,
  reloadInProgress,
  currentGitArgs,
}: CommitHistoryProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const [commits, setCommits] = React.useState<Commit[]>([]);
  const [hasMore, setHasMore] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [branch, setBranch] = React.useState<string | null>(null);

  // Determine selected commit from current git args
  const selectedHash = parseSelectedCommit(currentGitArgs);

  // Check if a commit matches the selected hash (handles both full and short hashes)
  const isCommitSelected = (commit: Commit) => {
    if (!selectedHash) return false;
    return commit.hash === selectedHash || commit.hash.startsWith(selectedHash) || selectedHash.startsWith(commit.hash);
  };

  const fetchCommits = React.useCallback(async (offset: number = 0) => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetch(apiUrl(`/api/commits/${repoIdx}?limit=25&offset=${offset}`));
      if (!response.ok) {
        throw new Error('Failed to fetch commits');
      }
      const data = await response.json();
      if (offset === 0) {
        setCommits(data.commits);
        setBranch(data.branch);
      } else {
        setCommits(prev => [...prev, ...data.commits]);
      }
      setHasMore(data.has_more);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [repoIdx]);

  React.useEffect(() => {
    if (isExpanded && commits.length === 0) {
      fetchCommits(0);
    }
  }, [isExpanded, commits.length, fetchCommits]);

  const handleSelectCommit = (commit: Commit) => {
    if (reloadInProgress) return;
    // Show this specific commit's changes
    onSelectCommit(commit.hash);
  };

  const handleSelectWorkingChanges = () => {
    if (reloadInProgress) return;
    onSelectWorkingChanges();
  };

  const loadMore = () => {
    if (!loading && hasMore) {
      fetchCommits(commits.length);
    }
  };

  return (
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
        <span style={{
          transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
          transition: 'transform 0.15s',
          display: 'inline-block',
        }}>
          ▶
        </span>
        <span>Commits</span>
        {branch && (
          <code style={{
            fontSize: '12px',
            color: '#0366d6',
            background: '#f1f8ff',
            padding: '2px 8px',
            borderRadius: '3px',
            fontFamily: MONO_FONT,
            fontWeight: 500,
          }}>
            {branch}
          </code>
        )}
        {commits.length > 0 && (
          <span style={{
            color: '#6a737d',
            fontWeight: 400,
            fontSize: '13px',
          }}>
            ({commits.length}{hasMore ? '+' : ''})
          </span>
        )}
      </button>

      {/* Commit list - collapsible */}
      {isExpanded && (
        <div style={{ maxHeight: '400px', overflowY: 'auto' }}>
          {error && (
            <div style={{
              padding: '12px',
              color: '#cb2431',
              background: '#ffeef0',
              fontSize: '13px',
              fontFamily: UI_FONT,
            }}>
              Error: {error}
            </div>
          )}

          {/* Working Changes option - always at top */}
          <div
            onClick={handleSelectWorkingChanges}
            style={{
              padding: '8px 12px',
              borderBottom: '1px solid #eaecef',
              cursor: reloadInProgress ? 'not-allowed' : 'pointer',
              background: selectedHash === null ? '#f1f8ff' : 'transparent',
              opacity: reloadInProgress ? 0.6 : 1,
              display: 'flex',
              alignItems: 'flex-start',
              gap: '10px',
              transition: 'background 0.1s',
            }}
            onMouseEnter={(e) => {
              if (!reloadInProgress && selectedHash !== null) {
                e.currentTarget.style.background = '#f6f8fa';
              }
            }}
            onMouseLeave={(e) => {
              if (selectedHash !== null) {
                e.currentTarget.style.background = 'transparent';
              }
            }}
          >
            <span style={{
              color: selectedHash === null ? '#0366d6' : '#959da5',
              fontSize: '10px',
              marginTop: '4px',
            }}>
              {selectedHash === null ? '●' : '○'}
            </span>
            <div style={{ flex: 1, minWidth: 0, fontFamily: UI_FONT }}>
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                marginBottom: '2px',
              }}>
                <code style={{
                  fontSize: '12px',
                  color: '#28a745',
                  background: '#dcffe4',
                  padding: '2px 6px',
                  borderRadius: '3px',
                  fontFamily: MONO_FONT,
                }}>
                  HEAD
                </code>
                <span style={{
                  fontSize: '13px',
                  color: '#24292e',
                }}>
                  Working Changes
                </span>
              </div>
              <div style={{
                fontSize: '12px',
                color: '#6a737d',
              }}>
                Unstaged and staged changes
              </div>
            </div>
          </div>

          {commits.map((commit) => (
            <div
              key={commit.hash}
              onClick={() => handleSelectCommit(commit)}
              style={{
                padding: '8px 12px',
                borderBottom: '1px solid #eaecef',
                cursor: reloadInProgress ? 'not-allowed' : 'pointer',
                background: isCommitSelected(commit) ? '#f1f8ff' : 'transparent',
                opacity: reloadInProgress ? 0.6 : 1,
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                transition: 'background 0.1s',
              }}
              onMouseEnter={(e) => {
                if (!reloadInProgress && !isCommitSelected(commit)) {
                  e.currentTarget.style.background = '#f6f8fa';
                }
              }}
              onMouseLeave={(e) => {
                if (!isCommitSelected(commit)) {
                  e.currentTarget.style.background = 'transparent';
                }
              }}
            >
              {/* Selection indicator */}
              <span style={{
                color: isCommitSelected(commit) ? '#0366d6' : '#959da5',
                fontSize: '10px',
                marginTop: '4px',
              }}>
                {isCommitSelected(commit) ? '●' : '○'}
              </span>

              {/* Commit info */}
              <div style={{ flex: 1, minWidth: 0, fontFamily: UI_FONT }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  marginBottom: '2px',
                }}>
                  <code style={{
                    fontSize: '12px',
                    color: '#0366d6',
                    background: '#f1f8ff',
                    padding: '2px 6px',
                    borderRadius: '3px',
                    fontFamily: MONO_FONT,
                  }}>
                    {commit.short_hash}
                  </code>
                  <span style={{
                    fontSize: '13px',
                    color: '#24292e',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                    flex: 1,
                  }}>
                    {commit.message}
                  </span>
                </div>
                <div style={{
                  fontSize: '12px',
                  color: '#6a737d',
                  display: 'flex',
                  gap: '12px',
                }}>
                  <span>{commit.author}</span>
                  <span>{commit.relative}</span>
                </div>
              </div>
            </div>
          ))}

          {/* Load more button */}
          {hasMore && (
            <button
              onClick={loadMore}
              disabled={loading}
              style={{
                width: '100%',
                padding: '10px',
                border: 'none',
                background: '#f6f8fa',
                color: '#0366d6',
                fontSize: '13px',
                fontFamily: UI_FONT,
                cursor: loading ? 'wait' : 'pointer',
                fontWeight: 500,
              }}
            >
              {loading ? 'Loading...' : 'Load more commits'}
            </button>
          )}

          {/* Loading state */}
          {loading && commits.length === 0 && (
            <div style={{
              padding: '20px',
              textAlign: 'center',
              color: '#6a737d',
              fontSize: '13px',
              fontFamily: UI_FONT,
            }}>
              Loading commits...
            </div>
          )}

          {/* Empty state */}
          {!loading && commits.length === 0 && !error && (
            <div style={{
              padding: '20px',
              textAlign: 'center',
              color: '#6a737d',
              fontSize: '13px',
              fontFamily: UI_FONT,
            }}>
              No commits found
            </div>
          )}
        </div>
      )}
    </div>
  );
}
