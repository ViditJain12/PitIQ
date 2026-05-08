import { create } from 'zustand'
import type { CircuitInfo, DriverInfo } from '../api/types'

type Mode = 'sandbox' | 'optimizer'

interface AppState {
  circuits: CircuitInfo[]
  drivers: DriverInfo[]
  selectedCircuit: string | null
  selectedDriver: string | null
  selectedYear: number
  selectedMode: Mode

  setCircuits: (c: CircuitInfo[]) => void
  setDrivers: (d: DriverInfo[]) => void
  setSelectedCircuit: (name: string | null) => void
  setSelectedDriver: (code: string | null) => void
  setSelectedYear: (y: number) => void
  setSelectedMode: (m: Mode) => void
}

export const useStore = create<AppState>(set => ({
  circuits: [],
  drivers: [],
  selectedCircuit: null,
  selectedDriver: null,
  selectedYear: 2024,
  selectedMode: 'sandbox',

  setCircuits: (circuits) => set({ circuits }),
  setDrivers: (drivers) => set({ drivers }),
  setSelectedCircuit: (selectedCircuit) => set({ selectedCircuit }),
  setSelectedDriver: (selectedDriver) => set({ selectedDriver }),
  setSelectedYear: (selectedYear) => set({ selectedYear }),
  setSelectedMode: (selectedMode) => set({ selectedMode }),
}))
