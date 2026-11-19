import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ChoiceCard } from '../components/choice-card';

const setup = () => { const pick = vi.fn(), skip = vi.fn(); render(<ChoiceCard question="How many holes?" options={['9 holes', '18 holes', 'Both']} onPick={pick} onSkip={skip} />); return { pick, skip, box: screen.getByRole('group') }; };

describe('ChoiceCard', () => {
  it('picks with a click, a number key, or the arrow keys and Enter', () => {
    const { pick, box } = setup();
    fireEvent.click(screen.getByText('18 holes')); expect(pick).toHaveBeenLastCalledWith('18 holes');
    fireEvent.keyDown(box, { key: '3' }); expect(pick).toHaveBeenLastCalledWith('Both');
    fireEvent.keyDown(box, { key: 'ArrowDown' }); fireEvent.keyDown(box, { key: 'Enter' }); expect(pick).toHaveBeenLastCalledWith('18 holes');
  });
  it('sends free text from the "something else" row and skips with Escape or the button', () => {
    const { pick, skip, box } = setup();
    const input = screen.getByLabelText(/Another answer|คำตอบอื่น/);
    fireEvent.change(input, { target: { value: '12 holes' } }); fireEvent.keyDown(input, { key: 'Enter' }); expect(pick).toHaveBeenLastCalledWith('12 holes');
    fireEvent.keyDown(box, { key: 'Escape' }); expect(skip).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getAllByRole('button', { name: /ข้าม|Skip/ })[0]); expect(skip).toHaveBeenCalledTimes(2);
  });
});
