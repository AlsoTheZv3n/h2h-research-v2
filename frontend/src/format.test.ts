import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { countLabel, formatAge, formatCount, formatNm } from './format'

/**
 * These exist because the rendered page showed "480.000 nM" on a German browser.
 * To an English reader that is 480 -- a potency misread by 1000x, decided by an OS
 * setting. Numbers in an English UI cannot be at the mercy of the viewer's locale.
 */
describe('formatNm', () => {
  it('uses en-US separators regardless of the runtime locale', () => {
    expect(formatNm(480000)).toBe('480,000')
    expect(formatNm(12.66)).toBe('12.66')
  })

  it('keeps sub-nanomolar precision instead of rounding it to zero', () => {
    // A 0.9 nM inhibitor rounded to "1" is a lie; rounded to "0" is a worse one.
    expect(formatNm(0.9)).toBe('0.9')
    expect(formatNm(0.005)).toBe('5.0e-3')
  })

  it('drops decimals nobody reads on large values', () => {
    expect(formatNm(50000.4)).toBe('50,000')
  })

  it('renders a missing value as a dash, not as zero', () => {
    expect(formatNm(null)).toBe('—')
    expect(formatNm(undefined)).toBe('—')
    // And an actual zero is still a zero.
    expect(formatNm(0)).toBe('0')
  })

  it('switches to exponential strictly BELOW 0.01, not at it', () => {
    // The boundary: 0.009 is too small for two decimals (would round to "0.01", a 10% lie), so it
    // goes exponential; 0.01 itself still reads cleanly as "0.01". A `<=` here would push 0.01 into
    // exponential needlessly.
    expect(formatNm(0.009)).toBe('9.0e-3')
    expect(formatNm(0.01)).toBe('0.01')
  })
})

describe('formatCount', () => {
  it('groups thousands the en-US way', () => {
    expect(formatCount(3856)).toBe('3,856')
    expect(formatCount(894)).toBe('894')
  })
})

describe('countLabel', () => {
  it('shows "X of Y" for a known-corpus subset', () => {
    expect(countLabel(412, 3922, true)).toBe('412 of 3,922 shown')
    // Scoping hides the tail even with no explicit filter: still a subset of Y.
    expect(countLabel(3641, 3922, false)).toBe('3,641 of 3,922 shown')
  })

  it('says "match", never "in catalog", when filtered but the corpus size is unknown', () => {
    // The regression this guards: with the size probe down, a filtered subset must not
    // read as the whole catalog. 3 hits for a query is "3 match", not "3 in catalog".
    expect(countLabel(3, null, true)).toBe('3 match')
  })

  it('says "in catalog" only for the unfiltered full view', () => {
    expect(countLabel(3922, null, false)).toBe('3,922 in catalog')
    // Whole corpus showing (data === catalogTotal) is not a subset.
    expect(countLabel(3922, 3922, false)).toBe('3,922 in catalog')
  })
})

/**
 * Freshness in words (E4). "Today" moves, so the clock is pinned per test rather than
 * compared to a hardcoded date -- the same reason the helper reads Date.now() at call time.
 */
describe('formatAge', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-21T12:00:00Z'))
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('reads the recent past in natural words, largest sensible unit', () => {
    expect(formatAge('2026-07-21T08:00:00Z')).toBe('today') // same day
    expect(formatAge('2026-07-20T12:00:00Z')).toBe('yesterday')
    expect(formatAge('2026-07-18T12:00:00Z')).toBe('3 days ago')
    expect(formatAge('2026-07-07T12:00:00Z')).toBe('2 weeks ago')
    expect(formatAge('2026-04-21T12:00:00Z')).toBe('3 months ago')
    expect(formatAge('2024-07-21T12:00:00Z')).toBe('2 years ago')
  })

  it('rolls up at the exact bucket edge to the larger unit (strictly-less-than boundaries)', () => {
    // The bucket cutoffs are `< 7`, `< 30`, `< 365`. A value sitting exactly ON a cutoff must fall
    // through to the LARGER unit -- 7 days is "last week", not "7 days ago"; 30 is "last month";
    // 365 is "last year". These edges are what a `<`→`<=` slip would flip, and nothing else pins
    // them (now = 2026-07-21T12:00:00Z).
    expect(formatAge('2026-07-14T12:00:00Z')).toBe('last week') // exactly 7 days
    expect(formatAge('2026-06-21T12:00:00Z')).toBe('last month') // exactly 30 days
    expect(formatAge('2025-07-21T12:00:00Z')).toBe('last year') // exactly 365 days
  })

  it('degrades to the raw string on an unparseable timestamp, never a fabricated "today"', () => {
    // The same discipline as the absolute date: show the bad value, do not invent freshness.
    expect(formatAge('not-a-date')).toBe('not-a-date')
  })
})
