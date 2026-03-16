import { useEffect, useState, useSyncExternalStore } from 'react'
import {
  connectWebSocket,
  getServerClockServerSnapshot,
  getServerClockSnapshot,
  subscribeServerClock,
} from '../api/websocket'

export function useNepalClock() {
  const serverClock = useSyncExternalStore(
    subscribeServerClock,
    getServerClockSnapshot,
    getServerClockServerSnapshot,
  )
  const [, setTick] = useState(0)

  useEffect(() => {
    connectWebSocket()
  }, [])

  useEffect(() => {
    const timer = setInterval(() => {
      setTick((value) => value + 1)
    }, 1000)

    return () => clearInterval(timer)
  }, [])

  const hasServerSync =
    serverClock.serverEpochMs !== null && serverClock.receivedAtPerfMs !== null

  let nowMs = Date.now()
  if (hasServerSync) {
    const serverEpochMs = serverClock.serverEpochMs!
    const receivedAtPerfMs = serverClock.receivedAtPerfMs!
    nowMs =
      serverEpochMs +
      Math.max(0, performance.now() - receivedAtPerfMs)
  }

  return {
    now: new Date(nowMs),
    isServerSynced: hasServerSync,
  }
}
