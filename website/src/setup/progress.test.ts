import { act, renderHook } from '@testing-library/react';
import { SETUP_PROGRESS_KEY } from '../constants/site';
import {
  clearProgress,
  markDone,
  markNotDone,
  readProgress,
  setChoice,
  setPlatform,
  setWay,
  useSetupProgress,
} from './progress';

beforeEach(() => {
  window.localStorage.clear();
  clearProgress();
});

describe('readProgress', () => {
  it('starts with nothing ticked and the computer guessed from the browser', () => {
    vi.spyOn(navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (Windows NT 10.0)');
    expect(readProgress()).toEqual({ platform: 'windows', way: 'by-hand', done: [], choices: {} });
  });

  it('ignores rubbish left by an older version', () => {
    window.localStorage.setItem(SETUP_PROGRESS_KEY, JSON.stringify({ done: 'install' }));
    expect(readProgress().done).toEqual([]);
    window.localStorage.setItem(SETUP_PROGRESS_KEY, 'not json');
    expect(readProgress().done).toEqual([]);
  });

  it('keeps step ids it does not know', () => {
    window.localStorage.setItem(
      SETUP_PROGRESS_KEY,
      JSON.stringify({ platform: 'linux', way: 'claude', done: ['from-a-newer-guide'] }),
    );
    markDone('install');
    expect(readProgress()).toEqual({
      platform: 'linux',
      way: 'claude',
      done: ['from-a-newer-guide', 'install'],
      choices: {},
    });
  });

  it('gives back the same object while nothing has changed', () => {
    expect(readProgress()).toBe(readProgress());
  });
});

describe('changing progress', () => {
  it('ticks and unticks a step, once each', () => {
    markDone('a');
    markDone('a');
    markDone('b');
    expect(readProgress().done).toEqual(['a', 'b']);
    markNotDone('a');
    expect(readProgress().done).toEqual(['b']);
    expect(JSON.parse(window.localStorage.getItem(SETUP_PROGRESS_KEY) ?? '')).toMatchObject({
      done: ['b'],
    });
  });

  it('remembers the computer and the way in', () => {
    setPlatform('linux');
    setWay('claude');
    expect(readProgress()).toMatchObject({ platform: 'linux', way: 'claude' });
  });

  it('forgets everything on clearProgress', () => {
    markDone('a');
    setWay('claude');
    clearProgress();
    expect(readProgress().done).toEqual([]);
    expect(readProgress().way).toBe('by-hand');
    expect(window.localStorage.getItem(SETUP_PROGRESS_KEY)).toBeNull();
  });

  it('still works in memory when the browser refuses to store', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota');
    });
    markDone('a');
    expect(readProgress().done).toEqual(['a']);
  });
});

describe('useSetupProgress', () => {
  it('follows every change', () => {
    const { result } = renderHook(() => useSetupProgress());
    expect(result.current.done).toEqual([]);
    act(() => markDone('install'));
    expect(result.current.done).toEqual(['install']);
    act(() => setPlatform('windows'));
    expect(result.current.platform).toBe('windows');
    act(() => clearProgress());
    expect(result.current.done).toEqual([]);
  });

  it('notices a change made in another tab', () => {
    const { result } = renderHook(() => useSetupProgress());
    window.localStorage.setItem(
      SETUP_PROGRESS_KEY,
      JSON.stringify({ platform: 'mac', way: 'by-hand', done: ['elsewhere'] }),
    );
    act(() => {
      window.dispatchEvent(new StorageEvent('storage', { key: SETUP_PROGRESS_KEY }));
    });
    expect(result.current.done).toEqual(['elsewhere']);
  });
});

describe('answers to the parts\' questions', () => {
  it('remembers an answer and replaces it when it changes', () => {
    setChoice('mailbox', 'gmail');
    expect(readProgress().choices).toEqual({ mailbox: 'gmail' });
    setChoice('mailbox', 'other');
    setChoice('computer', 'laptop');
    expect(readProgress().choices).toEqual({ mailbox: 'other', computer: 'laptop' });
  });

  it('treats progress saved before questions existed as unanswered', () => {
    window.localStorage.setItem(
      SETUP_PROGRESS_KEY,
      JSON.stringify({ platform: 'mac', way: 'by-hand', done: ['a'] }),
    );
    expect(readProgress()).toEqual({ platform: 'mac', way: 'by-hand', done: ['a'], choices: {} });
  });
});
