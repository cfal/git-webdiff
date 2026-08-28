/** @jest-environment jsdom */

import React from 'react';
import ReactDOM from 'react-dom';
import {act} from 'react-dom/test-utils';

import {DiffView} from '../DiffView';
import {getUnifiedFileData} from '../unified-api';

jest.mock('../unified-api', () => ({
  getUnifiedFileData: jest.fn(),
}));

const mockedGetUnifiedFileData = getUnifiedFileData as jest.MockedFunction<
  typeof getUnifiedFileData
>;

test('waits for the full response before rendering a previously truncated diff', async () => {
  mockedGetUnifiedFileData
    .mockResolvedValueOnce({
      idx: 0,
      thick: {
        idx: 0,
        a: 'large.txt',
        b: 'large.txt',
        type: 'change',
        num_add: 1,
        num_delete: 1,
      },
      content_a: null,
      content_b: null,
      diff_ops: [],
      truncated: true,
      truncated_lines: 1,
      truncated_bytes: 100,
    })
    .mockImplementationOnce(() => new Promise(() => undefined));

  const container = document.createElement('div');
  document.body.appendChild(container);

  await act(async () => {
    ReactDOM.render(
      <DiffView
        repoIdx={0}
        thinFilePair={{
          idx: 0,
          a: 'large.txt',
          b: 'large.txt',
          type: 'change',
          num_add: 1,
          num_delete: 1,
        }}
        imageDiffMode="side-by-side"
        pdiffMode="off"
        diffOptions={{}}
        normalizeJSON={false}
        changeImageDiffMode={jest.fn()}
        changePDiffMode={jest.fn()}
        changeDiffOptions={jest.fn()}
      />,
      container,
    );
  });

  const renderAnyway = Array.from(container.querySelectorAll('a')).find(link =>
    link.textContent?.includes('Render diff anyway'),
  );
  expect(renderAnyway).toBeDefined();

  act(() => {
    renderAnyway?.dispatchEvent(new MouseEvent('click', {bubbles: true, cancelable: true}));
  });

  expect(container.textContent).toContain('Loading full diff…');
  expect(mockedGetUnifiedFileData).toHaveBeenCalledTimes(2);

  ReactDOM.unmountComponentAtNode(container);
  container.remove();
});
