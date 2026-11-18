import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SearchLoading } from '../components/search-loading';

beforeEach(() => vi.useFakeTimers());
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe('search loading screen', () => {
  it('announces the wait to assistive technology and shows skeleton cards', () => {
    const { container } = render(<SearchLoading />);
    const status = screen.getByRole('status');
    expect(status.getAttribute('aria-busy')).toBe('true');
    expect(status.textContent).toContain('กำลังค้นหาในเอกสาร');
    expect(container.querySelectorAll('.search-skeleton')).toHaveLength(3);
  });

  it('explains a long wait only after a few seconds', () => {
    render(<SearchLoading />);
    expect(screen.queryByText(/ครั้งแรกอาจใช้เวลา/)).toBeNull();
    act(() => { vi.advanceTimersByTime(6100); });
    expect(screen.getByText(/ครั้งแรกอาจใช้เวลา/)).toBeTruthy();
  });
});
