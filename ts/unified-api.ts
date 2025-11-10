import {FilePair} from './CodeDiffContainer';
import {DiffRange} from './codediff/codes';
import {apiUrl} from './api-utils';

export interface UnifiedFileData {
  idx: number;
  thick: FilePair;
  content_a: string | null;
  content_b: string | null;
  diff_ops: DiffRange[];
  diff_error?: string;
  truncated?: boolean;
  truncated_lines?: number;
  truncated_bytes?: number;
}

/**
 * Fetches all data needed to render a file diff in a single request.
 * This includes thick diff metadata, file contents for both sides, and diff operations.
 *
 * @param repoIdx Repository index
 * @param idx File pair index
 * @param options Diff options flags
 * @param normalizeJson Whether to normalize JSON before diffing
 * @param noTruncate If true, fetch full content even if lines are very long
 */
export async function getUnifiedFileData(
  repoIdx: number,
  idx: number,
  options: string[],
  normalizeJson: boolean,
  noTruncate: boolean = false
): Promise<UnifiedFileData> {
  const params = new URLSearchParams();
  params.set('normalize_json', String(normalizeJson));
  if (options.length > 0) {
    params.set('options', options.join(','));
  }
  if (noTruncate) {
    params.set('no_truncate', '1');
  }

  const response = await fetch(apiUrl(`/file/${repoIdx}/${idx}?${params}`));
  if (!response.ok) {
    throw new Error(`Failed to fetch file data: ${response.statusText}`);
  }

  const data = await response.json();

  // Transform the response to match our expected types
  return {
    idx: data.idx,
    thick: data.thick,
    content_a: data.content_a,
    content_b: data.content_b,
    diff_ops: data.diff_ops || [],
    diff_error: data.diff_error,
    truncated: data.truncated,
    truncated_lines: data.truncated_lines,
    truncated_bytes: data.truncated_bytes
  };
}

// Cache for unified file data
const unifiedCache: Map<string, UnifiedFileData> = new Map();

/**
 * Get unified file data with caching.
 * Cache key includes repo index, file index, options, and normalizeJson flag.
 */
export async function getCachedUnifiedFileData(
  repoIdx: number,
  idx: number,
  options: string[],
  normalizeJson: boolean
): Promise<UnifiedFileData> {
  const cacheKey = `${repoIdx}-${idx}-${options.join(',')}-${normalizeJson}`;

  if (unifiedCache.has(cacheKey)) {
    return unifiedCache.get(cacheKey)!;
  }

  const data = await getUnifiedFileData(repoIdx, idx, options, normalizeJson);
  unifiedCache.set(cacheKey, data);
  return data;
}

/**
 * Clear the unified cache (useful when options change globally)
 */
export function clearUnifiedCache() {
  unifiedCache.clear();
}