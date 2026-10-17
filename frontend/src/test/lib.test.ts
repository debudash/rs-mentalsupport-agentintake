import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { targetSize, prepareImage } from '../lib/imagePrep';
import { IDLE_SECONDS, useIdle } from '../lib/useIdle';
import { ApiError } from '../lib/api';

describe('image preparer', () => {
  it('scales the long edge down to 2000 px and never up', () => {
    expect(targetSize(4032, 3024)).toEqual({ width: 2000, height: 1500 });
    expect(targetSize(3024, 4032)).toEqual({ width: 1500, height: 2000 });
    expect(targetSize(800, 600)).toEqual({ width: 800, height: 600 });
  });

  it('falls back to the original file when the browser cannot decode it', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('unsupported')));
    const file = new File(['x'], 'photo.heic', { type: 'image/heic' });
    expect(await prepareImage(file)).toBe(file);
  });
});

describe('idle detector', () => {
  afterEach(() => vi.useRealTimers());

  it('reports once after 45 seconds without activity', () => {
    vi.useFakeTimers();
    const onIdle = vi.fn();
    renderHook(() => useIdle(onIdle, true, 'intake'));
    act(() => vi.advanceTimersByTime((IDLE_SECONDS - 1) * 1000));
    expect(onIdle).not.toHaveBeenCalled();
    act(() => vi.advanceTimersByTime(2000));
    expect(onIdle).toHaveBeenCalledWith(IDLE_SECONDS);
    act(() => vi.advanceTimersByTime(IDLE_SECONDS * 3000));
    expect(onIdle).toHaveBeenCalledTimes(1);
  });

  it('activity resets the timer and inactive steps never report', () => {
    vi.useFakeTimers();
    const onIdle = vi.fn();
    renderHook(() => useIdle(onIdle, true, 'intake'));
    act(() => vi.advanceTimersByTime(40_000));
    act(() => {
      window.dispatchEvent(new Event('keydown'));
    });
    act(() => vi.advanceTimersByTime(40_000));
    expect(onIdle).not.toHaveBeenCalled();
    const inactive = vi.fn();
    renderHook(() => useIdle(inactive, false, 'done'));
    act(() => vi.advanceTimersByTime(100_000));
    expect(inactive).not.toHaveBeenCalled();
  });
});

describe('ApiError', () => {
  it('turns server details into a friendly sentence', () => {
    expect(new ApiError(422, 'Please confirm.').friendly).toBe('Please confirm.');
    expect(new ApiError(409, { message: 'Taken.' }).friendly).toBe('Taken.');
    expect(new ApiError(500, { weird: true }).friendly).toMatch(/progress is saved/);
  });
});
