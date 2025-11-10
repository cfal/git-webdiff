import React from 'react';
import { RepoEditDialog } from './RepoEditDialog';

interface Repo {
  label: string;
  path: string;
}

interface RepoManagementModalProps {
  initialRepos: Repo[];
  currentRepoLabel: string;
  onClose: () => void;
}

export function RepoManagementModal({
  initialRepos,
  currentRepoLabel,
  onClose,
}: RepoManagementModalProps) {
  const [localRepos, setLocalRepos] = React.useState<Repo[]>(initialRepos);
  const [editingIndex, setEditingIndex] = React.useState<number | null>(null);
  const [showAddDialog, setShowAddDialog] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [hasChanges, setHasChanges] = React.useState(false);

  const handleAddRepo = (label: string, path: string) => {
    setLocalRepos([...localRepos, { label, path }]);
    setHasChanges(true);
    setShowAddDialog(false);
  };

  const handleEditRepo = (index: number, label: string, path: string) => {
    const updated = [...localRepos];
    updated[index] = { label, path };
    setLocalRepos(updated);
    setHasChanges(true);
    setEditingIndex(null);
  };

  const handleRemoveRepo = (index: number) => {
    if (localRepos.length <= 1) return;

    const confirmed = window.confirm(
      `Remove '${localRepos[index].label}'? (Not saved until Apply)`
    );

    if (confirmed) {
      setLocalRepos(localRepos.filter((_, i) => i !== index));
      setHasChanges(true);
    }
  };

  const handleMoveUp = (index: number) => {
    if (index === 0) return;

    const updated = [...localRepos];
    [updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
    setLocalRepos(updated);
    setHasChanges(true);
  };

  const handleMoveDown = (index: number) => {
    if (index === localRepos.length - 1) return;

    const updated = [...localRepos];
    [updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
    setLocalRepos(updated);
    setHasChanges(true);
  };

  const handleApply = async () => {
    setSaving(true);
    setError(null);

    try {
      const response = await fetch('/api/repos/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ repos: localRepos }),
      });

      const data = await response.json();

      if (data.success) {
        // Check if current repo still exists
        const currentRepoStillExists = localRepos.some(
          (r) => r.label === currentRepoLabel
        );

        if (currentRepoStillExists) {
          // Current repo still exists, just reload
          window.location.reload();
        } else {
          // Current repo was removed, redirect to first repo
          window.location.href = `/?repo=${encodeURIComponent(localRepos[0].label)}`;
        }
      } else {
        setError(data.error);
        setSaving(false);
      }
    } catch (err: any) {
      setError(`Network error: ${err.message}`);
      setSaving(false);
    }
  };

  const handleCancel = () => {
    if (hasChanges) {
      const confirmed = window.confirm('Discard all changes?');
      if (!confirmed) return;
    }

    onClose();
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && !showAddDialog && editingIndex === null) {
      handleCancel();
    }
  };

  React.useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [hasChanges, showAddDialog, editingIndex]);

  const existingLabels = localRepos.map((r) => r.label);
  const existingPaths = localRepos.map((r) => r.path);

  return (
    <>
      {/* Backdrop */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0, 0, 0, 0.5)',
          zIndex: 999,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onClick={handleCancel}
      >
        {/* Modal */}
        <div
          style={{
            width: '600px',
            maxHeight: '80vh',
            backgroundColor: '#fff',
            borderRadius: '8px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            padding: '24px',
            fontFamily: 'sans-serif',
            display: 'flex',
            flexDirection: 'column',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
            <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>
              Manage Repositories
            </h2>
            <button
              onClick={handleCancel}
              disabled={saving}
              style={{
                background: 'none',
                border: 'none',
                fontSize: '24px',
                cursor: saving ? 'not-allowed' : 'pointer',
                color: '#666',
                padding: 0,
                width: '28px',
                height: '28px',
              }}
            >
              ×
            </button>
          </div>

          {/* Repo Count */}
          <div style={{ marginBottom: '12px', fontSize: '14px', color: '#586069' }}>
            Repositories ({localRepos.length})
          </div>

          {/* Repo List */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              marginBottom: '16px',
              maxHeight: '400px',
            }}
          >
            {localRepos.map((repo, index) => (
              <div
                key={index}
                style={{
                  backgroundColor: '#f6f8fa',
                  border: '1px solid #d1d5da',
                  borderRadius: '6px',
                  padding: '12px',
                  marginBottom: '8px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, fontSize: '14px', color: '#24292e' }}>
                    {repo.label}
                  </div>
                  <div style={{ fontSize: '12px', color: '#586069', fontFamily: 'monospace' }}>
                    {repo.path}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '4px', marginLeft: '12px' }}>
                  <button
                    onClick={() => handleMoveUp(index)}
                    disabled={index === 0 || saving}
                    title="Move up"
                    style={{
                      width: '28px',
                      height: '28px',
                      padding: 0,
                      border: '1px solid #ced4da',
                      borderRadius: '4px',
                      backgroundColor: '#fff',
                      cursor: index === 0 || saving ? 'not-allowed' : 'pointer',
                      opacity: index === 0 || saving ? 0.4 : 1,
                      fontSize: '14px',
                    }}
                  >
                    ↑
                  </button>
                  <button
                    onClick={() => handleMoveDown(index)}
                    disabled={index === localRepos.length - 1 || saving}
                    title="Move down"
                    style={{
                      width: '28px',
                      height: '28px',
                      padding: 0,
                      border: '1px solid #ced4da',
                      borderRadius: '4px',
                      backgroundColor: '#fff',
                      cursor: index === localRepos.length - 1 || saving ? 'not-allowed' : 'pointer',
                      opacity: index === localRepos.length - 1 || saving ? 0.4 : 1,
                      fontSize: '14px',
                    }}
                  >
                    ↓
                  </button>
                  <button
                    onClick={() => setEditingIndex(index)}
                    disabled={saving}
                    title="Edit"
                    style={{
                      padding: '0 8px',
                      height: '28px',
                      border: '1px solid #ced4da',
                      borderRadius: '4px',
                      backgroundColor: '#fff',
                      cursor: saving ? 'not-allowed' : 'pointer',
                      opacity: saving ? 0.4 : 1,
                      fontSize: '12px',
                      color: '#007bff',
                    }}
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleRemoveRepo(index)}
                    disabled={localRepos.length <= 1 || saving}
                    title="Remove"
                    style={{
                      width: '28px',
                      height: '28px',
                      padding: 0,
                      border: '1px solid #ced4da',
                      borderRadius: '4px',
                      backgroundColor: '#fff',
                      cursor: localRepos.length <= 1 || saving ? 'not-allowed' : 'pointer',
                      opacity: localRepos.length <= 1 || saving ? 0.4 : 1,
                      fontSize: '16px',
                      color: localRepos.length <= 1 || saving ? '#999' : '#dc3545',
                    }}
                  >
                    −
                  </button>
                </div>
              </div>
            ))}
          </div>

          {/* Add Button */}
          <button
            onClick={() => setShowAddDialog(true)}
            disabled={saving}
            style={{
              padding: '10px 16px',
              fontSize: '14px',
              fontWeight: 600,
              borderRadius: '4px',
              border: 'none',
              backgroundColor: saving ? '#999' : '#28a745',
              color: '#fff',
              cursor: saving ? 'not-allowed' : 'pointer',
              marginBottom: '16px',
            }}
          >
            + Add Repository
          </button>

          {/* Error Message */}
          {error && (
            <div
              style={{
                padding: '8px 12px',
                backgroundColor: '#f8d7da',
                border: '1px solid #f5c6cb',
                borderRadius: '4px',
                fontSize: '14px',
                color: '#721c24',
                marginBottom: '16px',
              }}
            >
              {error}
            </div>
          )}

          {/* Action Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px' }}>
            <button
              onClick={handleCancel}
              disabled={saving}
              style={{
                padding: '8px 20px',
                fontSize: '14px',
                fontWeight: 600,
                borderRadius: '4px',
                border: '1px solid #ced4da',
                backgroundColor: '#fff',
                color: '#495057',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.6 : 1,
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleApply}
              disabled={!hasChanges || saving}
              style={{
                padding: '8px 20px',
                fontSize: '14px',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                backgroundColor: !hasChanges || saving ? '#6c757d' : '#007bff',
                color: '#fff',
                cursor: !hasChanges || saving ? 'not-allowed' : 'pointer',
                opacity: !hasChanges || saving ? 0.6 : 1,
              }}
            >
              {saving ? 'Applying...' : 'Apply'}
            </button>
          </div>
        </div>
      </div>

      {/* Add Dialog */}
      {showAddDialog && (
        <RepoEditDialog
          mode="add"
          existingLabels={existingLabels}
          existingPaths={existingPaths}
          onSave={handleAddRepo}
          onCancel={() => setShowAddDialog(false)}
        />
      )}

      {/* Edit Dialog */}
      {editingIndex !== null && (
        <RepoEditDialog
          mode="edit"
          initialLabel={localRepos[editingIndex].label}
          initialPath={localRepos[editingIndex].path}
          existingLabels={existingLabels.filter((_, i) => i !== editingIndex)}
          existingPaths={existingPaths.filter((_, i) => i !== editingIndex)}
          onSave={(label, path) => handleEditRepo(editingIndex, label, path)}
          onCancel={() => setEditingIndex(null)}
        />
      )}
    </>
  );
}
