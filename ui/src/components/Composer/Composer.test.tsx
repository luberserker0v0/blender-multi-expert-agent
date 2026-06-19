import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Composer from './Composer'
import type { SessionSummary } from '../../types'

const mockSession: SessionSummary = {
  id: 'gui-20260514-001',
  title: 'Wooden Chair Session',
  updatedAt: 'just now',
}

function baseProps(overrides = {}) {
  return {
    currentSession: mockSession,
    currentSessionId: 'gui-20260514-001',
    taskInput: '',
    referenceText: '',
    referenceImages: [],
    canStartRun: true,
    canStopRun: false,
    startBlockedReason: '',
    liveDiagnosticsRunning: false,
    settingsOpen: false,
    progressStage: 'idle',
    workflowStatus: 'idle',
    activityState: 'idle',
    syncState: 'live',
    agentOrchestratorReady: false,
    mcpState: 'idle',
    composerExpanded: true,
    onToggleComposer: vi.fn(),
    onTaskInputChange: vi.fn(),
    onReferenceTextChange: vi.fn(),
    onReferenceImagePick: vi.fn(),
    onStartRun: vi.fn(),
    onStopRun: vi.fn(),
    onRunLiveDiagnostics: vi.fn(),
    onToggleSettings: vi.fn(),
    onToggleInspector: vi.fn(),
    onToggleRuntime: vi.fn(),
    ...overrides,
  }
}

describe('Composer', () => {
  it('renders Start enabled and Stop disabled in idle state', () => {
    render(<Composer {...baseProps()} />)

    const startBtn = screen.getByRole('button', { name: 'Start' })
    const stopBtn = screen.getByRole('button', { name: 'Stop' })

    expect(startBtn).not.toBeDisabled()
    expect(stopBtn).toBeDisabled()
  })

  it('renders Start disabled and Stop enabled in running state', () => {
    render(
      <Composer
        {...baseProps({ canStartRun: false, canStopRun: true })}
      />,
    )

    const startBtn = screen.getByRole('button', { name: 'Start' })
    const stopBtn = screen.getByRole('button', { name: 'Stop' })

    expect(startBtn).toBeDisabled()
    expect(stopBtn).not.toBeDisabled()
  })

  it('displays stage, workflow, and activity chips', () => {
    render(
      <Composer
        {...baseProps({
          progressStage: 'part_refinement',
          workflowStatus: 'running',
          activityState: 'streaming',
          syncState: 'resyncing',
        })}
      />,
    )

    expect(screen.getByText('stage: part_refinement')).toBeInTheDocument()
    expect(screen.getByText('workflow: running')).toBeInTheDocument()
    expect(screen.getByText('activity: streaming')).toBeInTheDocument()
    expect(screen.getByText('sync: resyncing')).toBeInTheDocument()
  })

  it('shows idle as default stage when progressStage is empty', () => {
    render(<Composer {...baseProps({ progressStage: '' })} />)

    expect(screen.getByText('stage: idle')).toBeInTheDocument()
  })

  it('displays AO ready status when agentOrchestratorReady is true', () => {
    render(<Composer {...baseProps({ agentOrchestratorReady: true })} />)

    expect(screen.getByText('AO: ready')).toBeInTheDocument()
  })

  it('displays AO not verified status when agentOrchestratorReady is false', () => {
    render(<Composer {...baseProps({ agentOrchestratorReady: false })} />)

    expect(screen.getByText('AO: not verified')).toBeInTheDocument()
  })

  it('displays MCP state', () => {
    render(<Composer {...baseProps({ mcpState: 'connected' })} />)

    expect(screen.getByText('MCP: connected')).toBeInTheDocument()
  })

  it('shows startBlockedReason when expanded and reason is provided', () => {
    render(
      <Composer
        {...baseProps({
          canStartRun: false,
          startBlockedReason: 'Task prompt is required to start a run.',
        })}
      />,
    )

    expect(
      screen.getByText('Task prompt is required to start a run.'),
    ).toBeInTheDocument()
  })

  it('fires onStartRun when Start button is clicked', async () => {
    const user = userEvent.setup()
    const onStartRun = vi.fn()
    render(<Composer {...baseProps({ onStartRun })} />)

    await user.click(screen.getByRole('button', { name: 'Start' }))
    expect(onStartRun).toHaveBeenCalledOnce()
  })

  it('fires onStopRun when Stop button is clicked and enabled', async () => {
    const user = userEvent.setup()
    const onStopRun = vi.fn()
    render(
      <Composer
        {...baseProps({ canStopRun: true, onStopRun })}
      />,
    )

    await user.click(screen.getByRole('button', { name: 'Stop' }))
    expect(onStopRun).toHaveBeenCalledOnce()
  })

  it('shows session title when currentSession is provided', () => {
    render(<Composer {...baseProps()} />)

    expect(screen.getByText('Wooden Chair Session')).toBeInTheDocument()
  })

  it('shows fallback title when currentSession is null', () => {
    render(
      <Composer
        {...baseProps({ currentSession: null, currentSessionId: '' })}
      />,
    )

    expect(screen.getByText('Blender Modeling Operator')).toBeInTheDocument()
  })
})
