import React from 'react';
import {FilePair} from './CodeDiffContainer';
import {DiffView, PerceptualDiffMode} from './DiffView';
import {ImageDiffMode} from './ImageDiffModeSelector';
import {filePairDisplayName} from './utils';
import {GitDiffOptions} from './diff-options';

interface FileViewProps {
  repoIdx: number;
  filePair: FilePair;
  isExpanded: boolean;
  onToggle: () => void;
  onHide: () => void;
  imageDiffMode: ImageDiffMode;
  pdiffMode: PerceptualDiffMode;
  diffOptions: Partial<GitDiffOptions>;
  normalizeJSON: boolean;
  changeImageDiffMode: (mode: ImageDiffMode) => void;
  changePDiffMode: React.Dispatch<React.SetStateAction<PerceptualDiffMode>>;
  changeDiffOptions: (options: Partial<GitDiffOptions>) => void;
}

function FileView({
  filePair,
  isExpanded,
  onToggle,
  onHide,
  ...diffProps
}: FileViewProps) {
  const hasStats = filePair.num_add !== null || filePair.num_delete !== null;
  
  const handleCopyFilename = (e: React.MouseEvent) => {
    e.stopPropagation();
    const filename = filePairDisplayName(filePair);
    navigator.clipboard.writeText(filename).then(() => {
      // Could add a toast notification here if desired
    }).catch(err => {
      console.error('Failed to copy filename:', err);
    });
  };
  
  return (
    <div className="file-diff-container" id={`file-${filePair.idx}`} data-file-path={filePairDisplayName(filePair)}>
      <div className="file-diff-header">
        <div onClick={onToggle} style={{display: 'flex', alignItems: 'center', flex: 1, gap: '8px'}}>
          <span className={`diff ${filePair.type}`} title={filePair.type} />
          <span className="file-diff-name">{filePairDisplayName(filePair)}</span>
          <button
            className="copy-filename-btn"
            onClick={handleCopyFilename}
            title="Copy filename"
            aria-label="Copy filename"
          >
            <svg width="16" height="16">
              <use href="#copy-icon" />
            </svg>
          </button>
          {hasStats && (
            <span className="file-diff-stats">
              {filePair.num_add !== null && filePair.num_add > 0 && (
                <span className="num-add">+{filePair.num_add}</span>
              )}
              {filePair.num_delete !== null && filePair.num_delete > 0 && (
                <span className="num-delete">-{filePair.num_delete}</span>
              )}
            </span>
          )}
        </div>
        <button
          className="hide-file-btn"
          onClick={(e) => {
            e.stopPropagation();
            onHide();
          }}
          title="Hide this file"
        >
          ×
        </button>
      </div>
      <div className="file-diff-content" style={{display: isExpanded ? 'block' : 'none'}}>
        <DiffView
          key={`diff-${filePair.idx}`}
          thinFilePair={filePair}
          {...diffProps}
        />
      </div>
    </div>
  );
}

export interface MultiFileViewProps {
  repoIdx: number;
  filePairs: FilePair[];
  imageDiffMode: ImageDiffMode;
  pdiffMode: PerceptualDiffMode;
  diffOptions: Partial<GitDiffOptions>;
  normalizeJSON: boolean;
  changeImageDiffMode: (mode: ImageDiffMode) => void;
  changePDiffMode: React.Dispatch<React.SetStateAction<PerceptualDiffMode>>;
  changeDiffOptions: (options: Partial<GitDiffOptions>) => void;
}

export function MultiFileView(props: MultiFileViewProps) {
  const {repoIdx, filePairs, ...diffProps} = props;
  const [expandedFiles, setExpandedFiles] = React.useState<Set<number>>(
    new Set(filePairs.map((_, idx) => idx))
  );
  const [hiddenFiles, setHiddenFiles] = React.useState<Set<number>>(new Set());

  // Calculate file counts by type and total line changes
  const {fileCounts, lineCounts} = React.useMemo(() => {
    const visiblePairs = filePairs.filter((_, idx) => !hiddenFiles.has(idx));
    const counts = { add: 0, delete: 0, change: 0, move: 0 };
    let totalLinesAdded = 0;
    let totalLinesDeleted = 0;
    
    visiblePairs.forEach(pair => {
      counts[pair.type as keyof typeof counts]++;
      if (pair.num_add !== null) totalLinesAdded += pair.num_add;
      if (pair.num_delete !== null) totalLinesDeleted += pair.num_delete;
    });
    
    return {
      fileCounts: counts,
      lineCounts: { added: totalLinesAdded, deleted: totalLinesDeleted }
    };
  }, [filePairs, hiddenFiles]);

  const toggleFile = (idx: number) => {
    setExpandedFiles(prev => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  const expandAll = () => {
    setExpandedFiles(new Set(filePairs.map((_, idx) => idx)));
  };

  const collapseAll = () => {
    setExpandedFiles(new Set());
  };

  // Show a nice message when there are no diffs
  if (filePairs.length === 0) {
    return (
      <div className="multi-file-view">
        <div className="files-summary">
          <div style={{
            padding: '40px 20px',
            textAlign: 'center',
            fontFamily: 'Arial, sans-serif',
            color: '#24292e'
          }}>
            <p style={{ margin: '0 0 8px 0', fontSize: '18px', fontWeight: 'bold' }}>
              No differences found
            </p>
            <p style={{ margin: 0, fontSize: '14px' }}>
              Try changing the git arguments above to compare different commits or branches
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="multi-file-view">
      <div className="files-summary">
        <h3 className="file-count-header">
          <span className="file-count-text">
            {(() => {
              const parts = [];
              if (fileCounts.add > 0) parts.push(`${fileCounts.add} added`);
              if (fileCounts.delete > 0) parts.push(`${fileCounts.delete} deleted`);
              if (fileCounts.change > 0) parts.push(`${fileCounts.change} changed`);
              if (fileCounts.move > 0) parts.push(`${fileCounts.move} moved`);
              return parts.join(', ') || '0 files';
            })()}
          </span>
          {(lineCounts.added > 0 || lineCounts.deleted > 0) && (
            <span className="line-count-summary">
              {lineCounts.added > 0 && <span className="num-add">+{lineCounts.added}</span>}
              {lineCounts.deleted > 0 && <span className="num-delete">-{lineCounts.deleted}</span>}
            </span>
          )}
        </h3>
        <div className="summary-list">
          {filePairs.map((filePair, idx) => {
            if (hiddenFiles.has(idx)) return null;
            const fileName = filePairDisplayName(filePair);
            const hasStats = filePair.num_add !== null || filePair.num_delete !== null;
            return (
              <div key={idx} className="summary-item">
                <button
                  className="hide-file-btn"
                  onClick={() => setHiddenFiles(prev => new Set([...prev, idx]))}
                  title="Hide this file"
                >
                  ×
                </button>
                <a href={`#file-${filePair.idx}`} className="summary-filename">
                  {fileName}
                  {hasStats && (
                    <span className="summary-stats">
                      {filePair.num_add !== null && filePair.num_add > 0 && (
                        <span className="summary-add">+{filePair.num_add}</span>
                      )}
                      {filePair.num_delete !== null && filePair.num_delete > 0 && (
                        <span className="summary-delete">-{filePair.num_delete}</span>
                      )}
                    </span>
                  )}
                </a>
              </div>
            );
          }).filter(Boolean)}
        </div>
        <div className="summary-controls">
          <button onClick={expandAll} className="expand-all-btn">
            Expand all
          </button>
          <button onClick={collapseAll} className="collapse-all-btn">
            Collapse all
          </button>
        </div>
      </div>
      {filePairs.map((filePair, idx) =>
        hiddenFiles.has(idx) ? null : (
          <FileView
            key={idx}
            repoIdx={repoIdx}
            filePair={filePair}
            isExpanded={expandedFiles.has(idx)}
            onToggle={() => toggleFile(idx)}
            onHide={() => setHiddenFiles(prev => new Set([...prev, idx]))}
            {...diffProps}
          />
        )
      ).filter(Boolean)}
    </div>
  );
}
