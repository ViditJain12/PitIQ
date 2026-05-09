import { useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { api } from './api/client'
import { useStore } from './store'
import Landing from './pages/Landing'
import Sandbox from './pages/Sandbox'
import Optimizer from './pages/Optimizer'
import Historical from './pages/Historical'

function DataLoader() {
  const setCircuits = useStore(s => s.setCircuits)
  const setDrivers = useStore(s => s.setDrivers)

  useEffect(() => {
    api.getCircuits().then(setCircuits).catch(console.error)
    api.getDrivers().then(setDrivers).catch(console.error)
  }, [setCircuits, setDrivers])

  return null
}

export default function App() {
  return (
    <BrowserRouter>
      <DataLoader />
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/sandbox" element={<Sandbox />} />
        <Route path="/optimizer" element={<Optimizer />} />
        <Route path="/historical" element={<Historical />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
