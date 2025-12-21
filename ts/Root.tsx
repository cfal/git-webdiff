import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { FilePair } from './CodeDiffContainer';
import { PerceptualDiffMode } from './DiffView';
import { isLegitKeypress } from './utils';
import { ImageDiffMode } from './ImageDiffModeSelector';
import { DiffOptionsControl } from './DiffOptions';
import { KeyboardShortcuts } from './codediff/KeyboardShortcuts';
import { Options, encodeOptions, ServerConfig, parseOptions, UpdateOptionsFn } from './options';
import { MultiFileView } from './MultiFileView';
import { apiUrl } from './api-utils';
import { CommandBar } from './CommandBar';
import { RepoSelector } from './RepoSelector';
import { RepoManagementModal } from './RepoManagementModal';
import { CommitHistory } from './CommitHistory';

interface Repo {
  label: string;
  path: string;
}

declare const repos: Repo[];
declare const pairs: FilePair[];
declare const current_repo_label: string;
declare const current_repo_idx: number;
declare const SERVER_CONFIG: ServerConfig;
declare const git_args: string[];
declare const watch_enabled: boolean;
declare const manage_repos_enabled: boolean;

// Hook for checking for diff updates (per-repo)
function useReloadDetection(repoIdx: number, pollInterval: number = 5000) {
  const [reloadAvailable, setReloadAvailable] = React.useState(false);
  const [watchEnabled, setWatchEnabled] = React.useState(false);
  const [reloadInProgress, setReloadInProgress] = React.useState(false);

  React.useEffect(() => {
    // Check for updates periodically
    const checkForUpdates = async () => {
      try {
        const response = await fetch(apiUrl(`/api/diff-changed/${repoIdx}`));
        if (response.ok) {
          const data = await response.json();
          setWatchEnabled(data.watch_enabled);

          // Show reload banner if diff has changed (checksum differs)
          if (data.changed) {
            setReloadAvailable(true);
          }
        }
      } catch (error) {
        console.error('Error checking for updates:', error);
      }
    };

    // Initial check
    checkForUpdates();

    // Poll periodically
    const interval = setInterval(checkForUpdates, pollInterval);

    return () => clearInterval(interval);
  }, [repoIdx, pollInterval]);

  const reload = React.useCallback(async (newGitArgs?: string[]) => {
    try {
      setReloadInProgress(true);
      setReloadAvailable(false);

      // This blocks until the backend completes the refresh
      const response = await fetch(apiUrl(`/api/server-reload/${repoIdx}`), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: newGitArgs ? JSON.stringify({ git_args: newGitArgs }) : undefined,
      });

      if (response.ok) {
        const data = await response.json();
        if (data.success) {
          // Refresh completed successfully, reload the page
          window.location.reload();
        } else {
          setReloadInProgress(false);
          console.error('Reload failed:', data.error);
          alert('Failed to reload: ' + data.error);
        }
      } else {
        setReloadInProgress(false);
        alert('Failed to trigger reload');
      }
    } catch (error) {
      setReloadInProgress(false);
      console.error('Error reloading:', error);
      alert('Failed to reload diff data');
    }
  }, [repoIdx]);

  return { reloadAvailable, watchEnabled, reload, reloadInProgress };
}

// Webdiff application root.
export function Root() {
  const [pdiffMode, setPDiffMode] = React.useState<PerceptualDiffMode>('off');
  const [imageDiffMode, setImageDiffMode] = React.useState<ImageDiffMode>('side-by-side');
  const [showKeyboardHelp, setShowKeyboardHelp] = React.useState(false);
  const [showOptions, setShowOptions] = React.useState(false);
  const [showManageRepos, setShowManageRepos] = React.useState(false);

  const [searchParams, setSearchParams] = useSearchParams();

  // Current repo data (from server)
  const currentRepoLabel = current_repo_label;
  const currentRepoIdx = current_repo_idx;

  // Repo switching
  const switchRepo = React.useCallback((label: string) => {
    // Update URL with new repo label
    window.location.href = apiUrl(`/?repo=${encodeURIComponent(label)}`);
  }, []);

  // Hot reload detection (per-repo)
  const { reloadAvailable, reload, reloadInProgress } = useReloadDetection(currentRepoIdx);

  // Set document title
  React.useEffect(() => {
    const repoInfo = repos.length > 1 ? ` [${currentRepoLabel}]` : '';
    document.title = `Diff: ${pairs.length} file${pairs.length !== 1 ? 's' : ''}${repoInfo}`;
  }, [currentRepoLabel]);

  const options = React.useMemo(() => parseOptions(searchParams), [searchParams]);
  // TODO: merge defaults into options
  const maxDiffWidth = options.maxDiffWidth ?? SERVER_CONFIG.webdiff.maxDiffWidth;
  const normalizeJSON = !!options.normalizeJSON;

  const setDiffOptions = React.useCallback(
    (newOptions: Partial<Options>) => {
      setSearchParams(encodeOptions(newOptions));
    },
    [setSearchParams],
  );

  const updateOptions = React.useCallback<UpdateOptionsFn>(
    update => {
      setDiffOptions({ ...options, ...(typeof update === 'function' ? update(options) : update) });
    },
    [options, setDiffOptions],
  );

  // Keyboard shortcuts
  React.useEffect(() => {
    const handleKeydown = (e: KeyboardEvent) => {
      if (!isLegitKeypress(e)) return;
      if (e.code === 'Slash' && e.shiftKey) {
        setShowKeyboardHelp(val => !val);
      } else if (e.code === 'Escape') {
        setShowKeyboardHelp(false);
      } else if (e.code === 'Period') {
        setShowOptions(val => !val);
      } else if (e.code === 'KeyZ') {
        updateOptions(o => ({ normalizeJSON: !o.normalizeJSON }));
      } else if (e.code === 'KeyR' && reloadAvailable) {
        reload();
      }
    };
    document.addEventListener('keydown', handleKeydown);
    return () => {
      document.removeEventListener('keydown', handleKeydown);
    };
  }, [updateOptions, reloadAvailable, reload]);

  const inlineStyle = `
  td.code {
    width: ${1 + maxDiffWidth}ch;
  }`;

  const repoSelectorElement = (
    <RepoSelector
      repos={repos}
      currentLabel={currentRepoLabel}
      manageReposEnabled={manage_repos_enabled}
      onSwitch={switchRepo}
      onManageRepos={() => setShowManageRepos(true)}
    />
  );

  return (
    <>
      <style>{inlineStyle}</style>
      <div style={{ padding: '8px', maxWidth: '1400px', margin: '0 auto' }}>
        {/* Command bar for git args and reload (includes repo selector) */}
        {watch_enabled ? (
          <CommandBar
            initialGitArgs={git_args}
            watchEnabled={watch_enabled}
            diffChanged={reloadAvailable}
            onReload={reload}
            reloadInProgress={reloadInProgress}
            repoSelector={repoSelectorElement}
          />
        ) : (
          /* Show repo selector even when watch is disabled */
          <div style={{
            background: '#fafbfc',
            border: '1px solid #d1d5da',
            borderRadius: '6px',
            padding: '8px',
            marginBottom: '8px',
          }}>
            {repoSelectorElement}
          </div>
        )}

        {/* Commit history panel */}
        <CommitHistory
          repoIdx={currentRepoIdx}
          onSelectCommit={(hash) => {
            // View this specific commit's changes
            reload([`${hash}^..${hash}`]);
          }}
          onSelectWorkingChanges={() => {
            // Back to working directory changes (no args = default)
            reload([]);
          }}
          reloadInProgress={reloadInProgress}
          currentGitArgs={git_args}
        />

        <div
          style={{
            position: 'sticky',
            float: 'right',
            marginTop: -10,
            marginLeft: 8,
            marginRight: 10,
            zIndex: 1,
            top: 10,
            background: '#e0e0e0',
            border: '1px solid #999',
            borderRadius: '6px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1), inset 0 1px 0 rgba(255,255,255,0.7)',
            padding: '4px',
            display: 'flex',
            gap: '4px',
            transition: 'margin-top 0.3s, top 0.3s',
          }}
        >
          <button
            style={{
              border: '1px solid #bbb',
              fontSize: '17px',
              background: 'linear-gradient(to bottom, #f5f5f5, #e8e8e8)',
              cursor: 'pointer',
              padding: '6px 14px',
              borderRadius: '4px',
              color: '#333',
              fontWeight: 'bold',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.8)',
            }}
            onMouseDown={(e) => {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #e8e8e8, #d8d8d8)';
              e.currentTarget.style.boxShadow = 'inset 0 1px 2px rgba(0,0,0,0.1)';
            }}
            onMouseUp={(e) => {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #f5f5f5, #e8e8e8)';
              e.currentTarget.style.boxShadow = 'inset 0 1px 0 rgba(255,255,255,0.8)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #f5f5f5, #e8e8e8)';
              e.currentTarget.style.boxShadow = 'inset 0 1px 0 rgba(255,255,255,0.8)';
            }}
            onClick={() => setShowOptions(val => !val)}
            title="Settings"
          >
            ⚙
          </button>
          <button
            style={{
              border: '1px solid #bbb',
              fontSize: '17px',
              background: 'linear-gradient(to bottom, #f5f5f5, #e8e8e8)',
              cursor: 'pointer',
              padding: '6px 14px',
              borderRadius: '4px',
              color: '#333',
              fontWeight: 'bold',
              boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.8)',
            }}
            onMouseDown={(e) => {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #e8e8e8, #d8d8d8)';
              e.currentTarget.style.boxShadow = 'inset 0 1px 2px rgba(0,0,0,0.1)';
            }}
            onMouseUp={(e) => {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #f5f5f5, #e8e8e8)';
              e.currentTarget.style.boxShadow = 'inset 0 1px 0 rgba(255,255,255,0.8)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #f5f5f5, #e8e8e8)';
              e.currentTarget.style.boxShadow = 'inset 0 1px 0 rgba(255,255,255,0.8)';
            }}
            onClick={() => window.scrollTo({ top: 0, behavior: 'instant' })}
            title="Scroll to top"
          >
            ↑
          </button>
        </div>
        <DiffOptionsControl
          options={options}
          updateOptions={updateOptions}
          defaultMaxDiffWidth={SERVER_CONFIG.webdiff.maxDiffWidth}
          isVisible={showOptions}
          setIsVisible={setShowOptions}
        />
        {showKeyboardHelp ? (
          <KeyboardShortcuts
            onClose={() => {
              setShowKeyboardHelp(false);
            }}
          />
        ) : null}
        <MultiFileView
          repoIdx={currentRepoIdx}
          filePairs={pairs}
          imageDiffMode={imageDiffMode}
          pdiffMode={pdiffMode}
          diffOptions={options}
          changeImageDiffMode={setImageDiffMode}
          changePDiffMode={setPDiffMode}
          changeDiffOptions={setDiffOptions}
          normalizeJSON={normalizeJSON}
        />
      </div>
      {showManageRepos && manage_repos_enabled && (
        <RepoManagementModal
          initialRepos={repos}
          currentRepoLabel={currentRepoLabel}
          onClose={() => setShowManageRepos(false)}
        />
      )}
    </>
  );
}
