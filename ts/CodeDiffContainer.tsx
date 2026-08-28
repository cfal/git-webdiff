import React from 'react';
import {GitDiffOptions} from './diff-options';
import {CodeDiff, PatchOptions} from './codediff/codediff';
import {guessLanguageUsingContents, guessLanguageUsingFileName} from './codediff/language';
import {ServerConfig} from './options';
import {DiffRange} from './codediff/codes';

interface BaseFilePair {
  idx: number;
  /** file name of left side of diff */
  a: string;
  /** file name of right side of diff */
  b: string;
  type: 'add' | 'delete' | 'move' | 'change'; // XXX check "change"
  /** Are there any changes to the file? Only set for "thick" diffs. */
  no_changes?: boolean;
  num_add: number | null;
  num_delete: number | null;
}

interface TextFilePair extends BaseFilePair {
  is_image_diff?: false;
}

// XXX this type is probably imprecise. What's a "thick" vs. "thin" diff?
export interface ImageFilePair extends BaseFilePair {
  is_image_diff: true;
  are_same_pixels: boolean;
  image_a: ImageFile;
  image_b: ImageFile;
  diffData?: ImageDiffData;
}

export type FilePair = TextFilePair | ImageFilePair;

export interface ImageFile {
  width: number;
  height: number;
  num_bytes: number;
}

export interface DiffBox {
  width: number;
  height: number;
  left: number;
  top: number;
  bottom: number;
  right: number;
}

export interface ImageDiffData {
  diffBounds: DiffBox;
}

// A "no changes" sign which only appears when applicable.
export function NoChanges(props: {filePair: FilePair; isEqualAfterNormalization: boolean}) {
  const {filePair, isEqualAfterNormalization} = props;
  let msg = null;
  if (filePair.no_changes) {
    msg = <>(File content is identical)</>;
  } else if (isEqualAfterNormalization) {
    msg = <>(File content is identical after normalization)</>;
  } else if (filePair.is_image_diff && filePair.are_same_pixels) {
    msg = (
      <>Pixels are the same, though file content differs (perhaps the headers are different?)</>
    );
  }
  return msg ? <div className="no-changes">{msg}</div> : null;
}

export interface CodeDiffContainerProps {
  filePair: FilePair;
  diffOptions: Partial<GitDiffOptions>;
  normalizeJSON: boolean;
  preloadedData: {
    content_a: string | null;
    content_b: string | null;
    diff_ops: DiffRange[];
    truncated?: boolean;
    truncated_lines?: number;
    truncated_bytes?: number;
  };
}

// A side-by-side diff of source code.
export function CodeDiffContainer(props: CodeDiffContainerProps) {
  const {filePair, normalizeJSON, preloadedData} = props;

  // Use the preloaded data directly - it's always available from DiffView
  const contents = {
    before: preloadedData.content_a,
    after: preloadedData.content_b,
    diffOps: preloadedData.diff_ops,
  };

  const isEqualAfterNormalization = React.useMemo(() => {
    return !filePair.no_changes && normalizeJSON && contents && contents.before == contents.after;
  }, [contents, filePair.no_changes, normalizeJSON]);

  return (
    <div>
      <div key={filePair.idx}>
        {contents ? (
          <FileDiff
            filePair={filePair}
            contentsBefore={contents.before}
            contentsAfter={contents.after}
            diffOps={contents.diffOps}
            isEqualAfterNormalization={!!isEqualAfterNormalization}
          />
        ) : (
          'Loading…'
        )}
      </div>
    </div>
  );
}

interface FileDiffProps {
  filePair: FilePair;
  contentsBefore: string | null;
  contentsAfter: string | null;
  diffOps: DiffRange[];
  isEqualAfterNormalization: boolean;
}

function extractFilename(path: string) {
  const parts = path.split('/');
  return parts[parts.length - 1];
}
const HIGHLIGHT_BLACKLIST = ['TODO', 'README', 'NOTES'];
declare const SERVER_CONFIG: ServerConfig;

function lengthOrZero(data: unknown[] | string | null | undefined) {
  return data?.length ?? 0;
}

function FileDiff(props: FileDiffProps) {
  const {filePair, contentsBefore, contentsAfter, diffOps, isEqualAfterNormalization} = props;
  const pathBefore = filePair.a;
  const pathAfter = filePair.b;
  // build the diff view and add it to the current DOM

  const lastOp = diffOps[diffOps.length - 1];
  // Empty operations are valid for identical files and can also be returned
  // alongside a backend diff error. Keep the view alive instead of crashing
  // the entire React tree while attempting to inspect the last operation.
  const numLines = lastOp
    ? Math.max(lastOp.before[1], lastOp.after[1])
    : Math.max(contentsBefore?.split('\n').length ?? 0, contentsAfter?.split('\n').length ?? 0);

  // First guess a language based on the file name.
  // Fall back to guessing based on the contents of the longer version.
  const path = pathBefore || pathAfter;
  const language = React.useMemo(() => {
    let language = guessLanguageUsingFileName(path);
    if (
      !language &&
      !HIGHLIGHT_BLACKLIST.includes(extractFilename(path)) &&
      numLines < SERVER_CONFIG.webdiff.maxLinesForSyntax
    ) {
      let byLength = [contentsBefore, contentsAfter];
      if (contentsAfter && lengthOrZero(contentsAfter) > lengthOrZero(contentsBefore)) {
        byLength = [byLength[1], byLength[0]];
      }
      language = byLength[0] ? guessLanguageUsingContents(byLength[0]) ?? null : null;
    }
    return language;
  }, [contentsAfter, contentsBefore, numLines, path]);

  const opts = React.useMemo(
    (): Partial<PatchOptions> => ({
      language,
      // TODO: thread through minJumpSize
    }),
    [language],
  );

  return (
    <div className="diff">
      <NoChanges filePair={filePair} isEqualAfterNormalization={isEqualAfterNormalization} />
      <CodeDiff beforeText={contentsBefore} afterText={contentsAfter} ops={diffOps} params={opts} />
    </div>
  );
}
