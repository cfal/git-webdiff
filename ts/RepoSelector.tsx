import React from 'react';

interface Repo {
  label: string;
  path: string;
}

interface RepoSelectorProps {
  repos: Repo[];
  currentLabel: string;
  manageReposEnabled: boolean;
  onSwitch: (label: string) => void;
  onManageRepos?: () => void;
}

export function RepoSelector({repos, currentLabel, manageReposEnabled, onSwitch, onManageRepos}: RepoSelectorProps) {
  const currentRepo = repos.find(r => r.label === currentLabel) || repos[0];

  if (!currentRepo) {
    return null;
  }

  // If manage-repos is disabled and there's only one repo, show as plain text
  if (!manageReposEnabled && repos.length === 1) {
    return (
      <span style={{
        fontWeight: 600,
        color: '#495057',
        fontSize: '14px',
      }}>
        {currentRepo.label}
      </span>
    );
  }

  // Otherwise, show combo box (either multiple repos, or manage-repos enabled)
  const handleChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const value = e.target.value;
    if (value === '__manage_repos__') {
      if (onManageRepos) {
        onManageRepos();
      }
      // Reset select to current repo
      e.target.value = currentLabel;
    } else {
      onSwitch(value);
    }
  };

  return (
    <select
      id="repo-select"
      value={currentLabel}
      onChange={handleChange}
      style={{
        padding: '4px 24px 4px 8px',
        fontSize: '14px',
        border: '1px solid #c1c8d4',
        borderRadius: '4px',
        background: '#fff',
        cursor: 'pointer',
        fontWeight: 600,
        color: '#495057',
        height: '32px',
        outline: 'none',
        WebkitAppearance: 'none',
        MozAppearance: 'none',
        appearance: 'none',
        backgroundImage: 'url("data:image/svg+xml;charset=UTF-8,%3csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 24 24\' fill=\'none\' stroke=\'currentColor\' stroke-width=\'2\' stroke-linecap=\'round\' stroke-linejoin=\'round\'%3e%3cpolyline points=\'6 9 12 15 18 9\'%3e%3c/polyline%3e%3c/svg%3e")',
        backgroundRepeat: 'no-repeat',
        backgroundPosition: 'right 8px center',
        backgroundSize: '16px',
      }}
      title="Switch repository"
    >
      {repos.map((repo) => (
        <option key={repo.label} value={repo.label}>
          {repo.label}
        </option>
      ))}
      {manageReposEnabled && (
        <>
          <option disabled>────────</option>
          <option value="__manage_repos__">Manage repos...</option>
        </>
      )}
    </select>
  );
}
