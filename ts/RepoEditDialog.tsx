import React from 'react';
import {apiUrl} from './api-utils';

interface RepoEditDialogProps {
  mode: 'add' | 'edit';
  initialLabel?: string;
  initialPath?: string;
  existingLabels: string[];
  existingPaths: string[];
  onSave: (label: string, path: string) => void;
  onCancel: () => void;
}

export function RepoEditDialog({
  mode,
  initialLabel = '',
  initialPath = '',
  existingLabels,
  existingPaths,
  onSave,
  onCancel,
}: RepoEditDialogProps) {
  const [label, setLabel] = React.useState(initialLabel);
  const [path, setPath] = React.useState(initialPath);
  const [validating, setValidating] = React.useState(false);
  const [validationResult, setValidationResult] = React.useState<{
    valid: boolean;
    error?: string;
  } | null>(null);

  const handleSave = async () => {
    // Frontend validation
    if (!label.trim()) {
      setValidationResult({ valid: false, error: 'Label cannot be empty' });
      return;
    }

    if (!path.trim()) {
      setValidationResult({ valid: false, error: 'Path cannot be empty' });
      return;
    }

    // Check for duplicates (skip checking against the original value in edit mode)
    if (mode === 'add' || label !== initialLabel) {
      if (existingLabels.includes(label)) {
        setValidationResult({ valid: false, error: `Label '${label}' already exists` });
        return;
      }
    }

    if (mode === 'add' || path !== initialPath) {
      if (existingPaths.includes(path)) {
        setValidationResult({ valid: false, error: `Path '${path}' already exists` });
        return;
      }
    }

    // Call API to validate
    setValidating(true);
    setValidationResult(null);

    try {
      const response = await fetch(apiUrl('/api/repos/validate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label, path }),
      });

      const data = await response.json();

      if (data.valid) {
        // Clear any error messages but don't show success message
        setValidationResult({ valid: true });
        // Call onSave to save
        onSave(label, path);
      } else {
        setValidationResult({ valid: false, error: data.error });
      }
    } catch (err: any) {
      setValidationResult({
        valid: false,
        error: `Network error: ${err.message}`,
      });
    } finally {
      setValidating(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !validating) {
      handleSave();
    } else if (e.key === 'Escape') {
      onCancel();
    }
  };

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
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
        onClick={onCancel}
      >
        {/* Dialog */}
        <div
          style={{
            width: '500px',
            backgroundColor: '#fff',
            borderRadius: '8px',
            boxShadow: '0 4px 20px rgba(0,0,0,0.15)',
            padding: '24px',
            fontFamily: 'sans-serif',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          {/* Header */}
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
            <h2 style={{ margin: 0, fontSize: '18px', fontWeight: 600 }}>
              {mode === 'add' ? 'Add Repository' : 'Edit Repository'}
            </h2>
            <button
              onClick={onCancel}
              style={{
                background: 'none',
                border: 'none',
                fontSize: '20px',
                cursor: 'pointer',
                color: '#666',
                padding: 0,
                width: '24px',
                height: '24px',
              }}
            >
              ×
            </button>
          </div>

          {/* Form */}
          <div style={{ marginBottom: '16px' }}>
            <label
              style={{
                display: 'block',
                marginBottom: '6px',
                fontSize: '14px',
                fontWeight: 600,
                color: '#24292e',
              }}
            >
              Label: *
            </label>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g., frontend"
              disabled={validating}
              autoFocus
              style={{
                width: '100%',
                padding: '8px 12px',
                fontSize: '14px',
                border: '1px solid #ced4da',
                borderRadius: '4px',
                fontFamily: 'sans-serif',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <div style={{ marginBottom: '16px' }}>
            <label
              style={{
                display: 'block',
                marginBottom: '6px',
                fontSize: '14px',
                fontWeight: 600,
                color: '#24292e',
              }}
            >
              Path: *
            </label>
            <input
              type="text"
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="e.g., /home/user/my-repo"
              disabled={validating}
              style={{
                width: '100%',
                padding: '8px 12px',
                fontSize: '14px',
                border: '1px solid #ced4da',
                borderRadius: '4px',
                fontFamily: 'monospace',
                boxSizing: 'border-box',
              }}
            />
          </div>

          {/* Validation Result - only show errors */}
          {validationResult && !validationResult.valid && (
            <div
              style={{
                marginBottom: '16px',
                padding: '8px 12px',
                borderRadius: '4px',
                fontSize: '14px',
                backgroundColor: '#f8d7da',
                color: '#721c24',
                border: '1px solid #f5c6cb',
              }}
            >
              ✗ {validationResult.error}
            </div>
          )}

          {/* Buttons */}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '12px', marginTop: '20px' }}>
            <button
              onClick={onCancel}
              disabled={validating}
              style={{
                padding: '8px 20px',
                fontSize: '14px',
                fontWeight: 600,
                borderRadius: '4px',
                border: '1px solid #ced4da',
                backgroundColor: '#fff',
                color: '#495057',
                cursor: validating ? 'not-allowed' : 'pointer',
                opacity: validating ? 0.6 : 1,
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={validating}
              style={{
                padding: '8px 20px',
                fontSize: '14px',
                fontWeight: 600,
                borderRadius: '4px',
                border: 'none',
                backgroundColor: validating ? '#6c757d' : '#007bff',
                color: '#fff',
                cursor: validating ? 'not-allowed' : 'pointer',
                opacity: validating ? 0.6 : 1,
              }}
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </>
  );
}
