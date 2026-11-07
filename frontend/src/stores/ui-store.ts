import { create } from 'zustand'

interface UiState {
  selectedModeId: string | null
  previewOpen: boolean
  ackWarnings: string[]
  activeRunId: string | null
  setSelectedModeId: (modeId: string | null) => void
  openPreview: (modeId: string) => void
  closePreview: () => void
  toggleAckWarning: (code: string) => void
  setAckWarnings: (codes: string[]) => void
  setActiveRunId: (runId: string | null) => void
  resetFlow: () => void
}

export const useUiStore = create<UiState>((set) => ({
  selectedModeId: null,
  previewOpen: false,
  ackWarnings: [],
  activeRunId: null,
  setSelectedModeId: (modeId) => set({ selectedModeId: modeId }),
  openPreview: (modeId) =>
    set({ selectedModeId: modeId, previewOpen: true, ackWarnings: [] }),
  closePreview: () => set({ previewOpen: false }),
  toggleAckWarning: (code) =>
    set((state) => ({
      ackWarnings: state.ackWarnings.includes(code)
        ? state.ackWarnings.filter((item) => item !== code)
        : [...state.ackWarnings, code],
    })),
  setAckWarnings: (codes) => set({ ackWarnings: codes }),
  setActiveRunId: (runId) => set({ activeRunId: runId }),
  resetFlow: () =>
    set({
      selectedModeId: null,
      previewOpen: false,
      ackWarnings: [],
      activeRunId: null,
    }),
}))
