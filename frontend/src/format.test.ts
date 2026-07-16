import { describe, expect, it } from 'vitest'
import { formatCount, formatNm } from './format'

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
})

describe('formatCount', () => {
  it('groups thousands the en-US way', () => {
    expect(formatCount(3856)).toBe('3,856')
    expect(formatCount(894)).toBe('894')
  })
})
