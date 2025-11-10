import React from 'react';

interface CommandBarProps {
  initialGitArgs: string[];
  watchEnabled: boolean;
  diffChanged: boolean;
  onReload: (newGitArgs?: string[]) => void;
  reloadInProgress: boolean;
  repoSelector?: React.ReactNode;
}

export function CommandBar({
  initialGitArgs,
  watchEnabled,
  diffChanged,
  onReload,
  reloadInProgress,
  repoSelector,
}: CommandBarProps) {
  const [gitArgs, setGitArgs] = React.useState(initialGitArgs.join(' '));
  const argsChanged = gitArgs !== initialGitArgs.join(' ');

  const handleReload = () => {
    if (argsChanged) {
      // Send new args to server
      const newArgs = gitArgs.trim().split(/\s+/).filter(arg => arg);
      onReload(newArgs);
    } else {
      // Just reload with same args
      onReload(undefined);
    }
  };

  return (
    <div
      style={{
        background: '#fafbfc',
        border: '1px solid #d1d5da',
        borderRadius: '6px',
        padding: '8px',
        marginBottom: '8px',
        fontFamily: 'sans-serif',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1, minWidth: '300px' }}>
          {repoSelector}
          <span style={{ fontWeight: 600, color: '#495057', fontSize: '14px' }}>
            $ git diff
          </span>
          <input
            type="text"
            value={gitArgs}
            onChange={(e) => setGitArgs(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && (argsChanged || diffChanged) && !reloadInProgress) {
                handleReload();
              }
            }}
            placeholder="[arguments] (eg. HEAD~3..HEAD)"
            disabled={reloadInProgress}
            style={{
              flex: 1,
              padding: '8px 12px',
              border: '1px solid #ced4da',
              borderRadius: '4px',
              fontSize: '14px',
              fontFamily: 'monospace',
              background: '#fff',
              outline: 'none',
              transition: 'border-color 0.15s',
            }}
            onFocus={(e) => {
              e.currentTarget.style.borderColor = '#80bdff';
              e.currentTarget.style.boxShadow = '0 0 0 0.2rem rgba(0,123,255,.25)';
            }}
            onBlur={(e) => {
              e.currentTarget.style.borderColor = '#ced4da';
              e.currentTarget.style.boxShadow = 'none';
            }}
          />
        </div>
        <button
          onClick={handleReload}
          disabled={!argsChanged && !diffChanged || reloadInProgress}
          style={{
            padding: '8px 20px',
            borderRadius: '4px',
            border: 'none',
            fontWeight: 600,
            fontSize: '14px',
            cursor: (!argsChanged && !diffChanged) || reloadInProgress ? 'not-allowed' : 'pointer',
            background: (!argsChanged && !diffChanged) || reloadInProgress
              ? 'linear-gradient(to bottom, #e9ecef, #dee2e6)'
              : 'linear-gradient(to bottom, #28a745, #218838)',
            color: (!argsChanged && !diffChanged) || reloadInProgress ? '#6c757d' : '#fff',
            boxShadow: (!argsChanged && !diffChanged) || reloadInProgress
              ? 'none'
              : '0 1px 3px rgba(0,0,0,0.2)',
            opacity: (!argsChanged && !diffChanged) || reloadInProgress ? 0.6 : 1,
            transition: 'all 0.15s',
          }}
          onMouseEnter={(e) => {
            if (!(!argsChanged && !diffChanged) && !reloadInProgress) {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #218838, #1e7e34)';
            }
          }}
          onMouseLeave={(e) => {
            if (!(!argsChanged && !diffChanged) && !reloadInProgress) {
              e.currentTarget.style.background = 'linear-gradient(to bottom, #28a745, #218838)';
            }
          }}
        >
          {reloadInProgress ? 'Reloading...' : 'Reload'}
        </button>
      </div>
      {watchEnabled && diffChanged && !argsChanged && (
        <div
          style={{
            marginTop: '6px',
            padding: '8px 12px',
            background: '#fff3cd',
            border: '1px solid #ffc107',
            borderRadius: '4px',
            color: '#856404',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <span style={{ fontSize: '16px' }}>ℹ️</span>
          <span>
            The diff has changed since loading. Press <strong>Reload</strong> or <kbd style={{
              background: '#fff',
              border: '1px solid #ccc',
              borderRadius: '3px',
              padding: '2px 6px',
              fontFamily: 'monospace',
              fontSize: '11px',
            }}>R</kbd> to update.
          </span>
        </div>
      )}
    </div>
  );
}
