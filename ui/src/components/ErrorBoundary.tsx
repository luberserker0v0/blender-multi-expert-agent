import { Component, type ErrorInfo, type ReactNode } from 'react'

interface ErrorBoundaryProps {
  children: ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
  message: string
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
    message: '',
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return {
      hasError: true,
      message: error.message || 'Unknown React runtime error',
    }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('React UI crashed', error, errorInfo)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-[linear-gradient(180deg,_#f7f3eb_0%,_#eef3f6_48%,_#e6ecef_100%)] px-6 py-10 text-slate-900">
          <div className="mx-auto max-w-3xl rounded-[28px] border border-rose-100 bg-white/90 p-8 shadow-xl shadow-slate-900/10">
            <p className="text-xs uppercase tracking-[0.24em] text-rose-500">UI Runtime Error</p>
            <h1 className="mt-2 font-display text-3xl text-slate-950">The React workspace hit an error.</h1>
            <p className="mt-4 text-sm leading-7 text-slate-700">
              This is usually caused by stale browser storage or unexpected progress data. Refresh the page once. If
              it still happens, clear this app&apos;s local storage and try again.
            </p>
            <pre className="mt-6 overflow-x-auto rounded-3xl bg-slate-950 px-4 py-4 font-mono text-xs text-slate-100">
              {this.state.message}
            </pre>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
