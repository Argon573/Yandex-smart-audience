import { create } from 'zustand'

interface TelemetryState {
  lastFetchedAt: number | null
  nowTick: number
  markFetched: (ts?: number) => void
  tick: () => void
}

export const useTelemetryStore = create<TelemetryState>((set) => ({
  lastFetchedAt: null,
  nowTick: Date.now(),
  markFetched: (ts = Date.now()) => set({ lastFetchedAt: ts }),
  tick: () => set({ nowTick: Date.now() }),
}))
