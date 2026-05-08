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
  seasonDrivers: Record<number, DriverInfo[]>
  seasonCircuits: Record<number, CircuitInfo[]>

  setCircuits: (c: CircuitInfo[]) => void
  setDrivers: (d: DriverInfo[]) => void
  setSelectedCircuit: (name: string | null) => void
  setSelectedDriver: (code: string | null) => void
  setSelectedYear: (y: number) => void
  setSelectedMode: (m: Mode) => void
  setSeasonDrivers: (year: number, drivers: DriverInfo[]) => void
  setSeasonCircuits: (year: number, circuits: CircuitInfo[]) => void
}

export const useStore = create<AppState>(set => ({
  circuits: [],
  drivers: [],
  selectedCircuit: null,
  selectedDriver: null,
  selectedYear: 2024,
  selectedMode: 'sandbox',
  seasonDrivers: {},
  seasonCircuits: {},

  setCircuits: (circuits) => set({ circuits }),
  setDrivers: (drivers) => set({ drivers }),
  setSelectedCircuit: (selectedCircuit) => set({ selectedCircuit }),
  setSelectedDriver: (selectedDriver) => set({ selectedDriver }),
  setSelectedYear: (selectedYear) => set({ selectedYear }),
  setSelectedMode: (selectedMode) => set({ selectedMode }),
  setSeasonDrivers: (year, drivers) =>
    set(s => ({ seasonDrivers: { ...s.seasonDrivers, [year]: drivers } })),
  setSeasonCircuits: (year, circuits) =>
    set(s => ({ seasonCircuits: { ...s.seasonCircuits, [year]: circuits } })),
}))
