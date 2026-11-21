import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { AttachCard, AttachPreview, kindOf, sizeLabel } from '../components/attachment-preview';

afterEach(cleanup);
const img = { name: 'chart.png', size: 2048, type: 'image/png', url: 'blob:x' };

it('classifies files by type or extension', () => {
  expect(kindOf('a.JPG')).toBe('image'); expect(kindOf('b.pdf')).toBe('pdf'); expect(kindOf('c.csv')).toBe('text');
  expect(kindOf('d.xlsx')).toBe('sheet'); expect(kindOf('e.pptx')).toBe('slides'); expect(kindOf('f.docx')).toBe('doc');
  expect(sizeLabel(2048)).toBe('2 KB'); expect(sizeLabel(3 * 1048576)).toBe('3.0 MB');
});

it('shows a thumbnail for a picture and opens the preview', () => {
  let opened = 0; render(<AttachCard a={img} onOpen={() => opened++} />);
  expect(screen.getByAltText('chart.png').getAttribute('src')).toBe('blob:x');
  fireEvent.click(screen.getByRole('button')); expect(opened).toBe(1);
});

it('shows a type icon and a remove button for a document', () => {
  let removed = 0; render(<AttachCard a={{ name: 'plan.docx', size: 10, type: '', url: 'blob:y' }} onOpen={() => {}} onRemove={() => removed++} />);
  expect(screen.queryByRole('img')).toBeNull(); fireEvent.click(screen.getByLabelText(/plan\.docx/, { selector: '[aria-label^="ลบ"],[aria-label^="Delete"]' })); expect(removed).toBe(1);
});

it('previews a picture large and an Office file with a download link', () => {
  const { unmount } = render(<AttachPreview a={img} onClose={() => {}} />);
  expect(screen.getAllByAltText('chart.png').length).toBe(1); unmount();
  render(<AttachPreview a={{ name: 'a.xlsx', size: 5, type: '', url: 'blob:z' }} onClose={() => {}} />);
  expect(document.querySelector('a[download="a.xlsx"]')).not.toBeNull();
});
