import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import type { TdlVerdict } from '../../api/types'
import { TdlBadge } from './TdlBadge'

const tchem: TdlVerdict = {
  level: 'Tchem',
  label: 'chemical matter, none approved',
  criteria: [
    { label: 'Approved drug (anywhere)', state: 'fail' },
    { label: 'In clinical development', state: 'fail' },
    { label: 'Potent ligand in catalog', state: 'pass' },
  ],
}

describe('TdlBadge', () => {
  it('shows the level and a self-explaining label', () => {
    render(<TdlBadge verdict={tchem} />)
    const badge = screen.getByTestId('tdl-Tchem')
    expect(badge).toHaveTextContent('Tchem')
    expect(badge).toHaveTextContent('chemical matter, none approved')
  })

  it('carries the pass/fail criteria in the title, with "unknown" as a distinct mark', () => {
    const tdark: TdlVerdict = {
      level: 'Tdark',
      label: 'not measured',
      criteria: [
        { label: 'Approved drug (anywhere)', state: 'unknown' },
        { label: 'Potent ligand in catalog', state: 'fail' },
      ],
    }
    render(<TdlBadge verdict={tdark} />)
    const title = screen.getByTestId('tdl-Tdark').getAttribute('title') ?? ''
    // unknown reads as a distinct mark, never a false ✗.
    expect(title).toContain('Approved drug (anywhere): –')
    expect(title).toContain('Potent ligand in catalog: ✗')
  })

  it('renders the backend self-explaining label, so an unresolved Tchem never claims "none approved"', () => {
    // OT never resolved the drug status; a potent ligand still makes this Tchem, but the verdict's
    // own label says "approval not measured". The badge must show THAT, not a hardcoded per-level
    // "none approved" -- claiming no approval from an unmeasured input is the honest-state collapse.
    const unresolved: TdlVerdict = {
      level: 'Tchem',
      label: 'chemical matter, approval not measured',
      criteria: [
        { label: 'Approved drug (anywhere)', state: 'unknown' },
        { label: 'Potent ligand in catalog', state: 'pass' },
      ],
    }
    render(<TdlBadge verdict={unresolved} />)
    const badge = screen.getByTestId('tdl-Tchem')
    expect(badge).toHaveTextContent('chemical matter, approval not measured')
    expect(badge).not.toHaveTextContent('none approved')
  })

  it('gives each level a distinct fill so they never blur', () => {
    const levels: TdlVerdict['level'][] = ['Tclin', 'Tchem', 'Tbio', 'Tdark']
    const classes = levels.map((level) => {
      const { unmount } = render(
        <TdlBadge verdict={{ level, label: level, criteria: [] }} />,
      )
      const cls = screen.getByTestId(`tdl-${level}`).className
      unmount()
      return cls
    })
    expect(new Set(classes).size).toBe(4)
  })
})
