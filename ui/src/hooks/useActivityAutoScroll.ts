import { useEffect, useRef } from 'react'

interface UseActivityAutoScrollOptions {
  itemCount: number
  onScrollToLatest?: () => void
  onScroll?: (event: React.UIEvent<HTMLDivElement>) => void
}

export function useActivityAutoScroll({
  itemCount,
  onScrollToLatest,
  onScroll,
}: UseActivityAutoScrollOptions) {
  const scrollRef = useRef<HTMLDivElement | null>(null)
  const endRef = useRef<HTMLDivElement | null>(null)
  const shouldAutoScrollRef = useRef(true)
  const lastItemCountRef = useRef(0)

  useEffect(() => {
    const node = endRef.current
    const hasNewItems = itemCount > lastItemCountRef.current
    lastItemCountRef.current = itemCount
    if (!node || !hasNewItems || !shouldAutoScrollRef.current) return
    if (typeof node.scrollIntoView === 'function') {
      node.scrollIntoView({ block: 'end', behavior: 'smooth' })
    }
  }, [itemCount])

  const handleScroll = () => {
    const node = scrollRef.current
    if (!node) return
    const distanceToBottom = node.scrollHeight - node.scrollTop - node.clientHeight
    shouldAutoScrollRef.current = distanceToBottom < 96
    onScroll?.({} as React.UIEvent<HTMLDivElement>)
  }

  const scrollToLatest = () => {
    shouldAutoScrollRef.current = true
    if (endRef.current && typeof endRef.current.scrollIntoView === 'function') {
      endRef.current.scrollIntoView({ block: 'end', behavior: 'smooth' })
    }
    onScrollToLatest?.()
  }

  return {
    scrollRef,
    endRef,
    handleScroll,
    scrollToLatest,
  }
}
