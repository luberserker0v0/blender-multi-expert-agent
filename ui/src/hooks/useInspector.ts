import { useCallback, useState } from 'react'
import type { InspectorSelection } from '../components/inspector'

export default function useInspector() {
  const [inspectorSelection, setInspectorSelection] = useState<InspectorSelection>(null)
  const [expandedActivityIds, setExpandedActivityIds] = useState<string[]>([])

  const toggleExpandedActivityId = useCallback((itemId: string) => {
    setExpandedActivityIds((current) =>
      current.includes(itemId) ? current.filter((value) => value !== itemId) : [...current, itemId],
    )
  }, [])

  return {
    inspectorSelection,
    expandedActivityIds,
    setInspectorSelection,
    setExpandedActivityIds,
    toggleExpandedActivityId,
  }
}
