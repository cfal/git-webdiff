import React from 'react';
import {CodeDiffContainer, FilePair} from './CodeDiffContainer';
import {GitDiffOptions, gitDiffOptionsToFlags} from './diff-options';
import {getUnifiedFileData, UnifiedFileData} from './unified-api';
import {ImageDiff} from './ImageDiff';
import {ImageDiffMode} from './ImageDiffModeSelector';

export type PerceptualDiffMode = 'off' | 'bbox' | 'pixels';

export interface Props {
  repoIdx: number;
  thinFilePair: FilePair;
  imageDiffMode: ImageDiffMode;
  pdiffMode: PerceptualDiffMode;
  diffOptions: Partial<GitDiffOptions>;
  normalizeJSON: boolean;
  changeImageDiffMode: (mode: ImageDiffMode) => void;
  changePDiffMode: React.Dispatch<React.SetStateAction<PerceptualDiffMode>>;
  changeDiffOptions: (options: Partial<GitDiffOptions>) => void;
}

export function DiffView(props: Props) {
  const {repoIdx, diffOptions, thinFilePair, normalizeJSON} = props;
  const [unifiedData, setUnifiedData] = React.useState<UnifiedFileData | null>(null);
  const [noTruncate, setNoTruncate] = React.useState(false);

  React.useEffect(() => {
    (async () => {
      try {
        // Fetch everything in one request
        const data = await getUnifiedFileData(
          repoIdx,
          thinFilePair.idx,
          gitDiffOptionsToFlags(diffOptions),
          normalizeJSON,
          noTruncate
        );
        setUnifiedData(data);
      } catch (e) {
        console.error('Failed to load file data:', e);
      }
    })();
  }, [repoIdx, thinFilePair.idx, diffOptions, normalizeJSON, noTruncate]);

  if (!unifiedData) {
    return <div>Loading…</div>;
  }

  // Check if file was truncated
  if (unifiedData.truncated && !noTruncate) {
    const bytesInMB = (unifiedData.truncated_bytes || 0) / (1024 * 1024);
    return (
      <div className="diff">
        <table className="diff">
          <tbody>
            <tr>
              <td className="code equal before suppressed-large-diff">
                <p>⚠️ This file may be minified and the diff may slow down the browser. ⚠️</p>
                <p>
                  {unifiedData.truncated_lines} lines exceed 500 characters
                  ({bytesInMB.toFixed(2)} MB would be hidden)
                </p>
                <p>
                  <a
                    href="#"
                    onClick={e => {
                      e.preventDefault();
                      setNoTruncate(true);
                    }}>
                    Render diff anyway
                  </a>
                </p>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    );
  }

  // Use the thick data from unified response
  const filePair = {
    ...unifiedData.thick,
    idx: thinFilePair.idx
  };

  let diffEl;
  if (filePair.is_image_diff) {
    diffEl = <ImageDiff filePair={filePair} {...props} />;
  } else {
    // Pass the already-loaded data to avoid duplicate fetching
    diffEl = (
      <CodeDiffContainer
        filePair={filePair}
        diffOptions={diffOptions}
        normalizeJSON={normalizeJSON}
        preloadedData={{
          content_a: unifiedData.content_a,
          content_b: unifiedData.content_b,
          diff_ops: unifiedData.diff_ops,
          truncated: unifiedData.truncated,
          truncated_lines: unifiedData.truncated_lines,
          truncated_bytes: unifiedData.truncated_bytes
        }}
      />
    );
  }

  return diffEl;
}
