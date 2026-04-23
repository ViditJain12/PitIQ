import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Landing from './pages/Landing'
import Sandbox from './pages/Sandbox'
import Optimizer from './pages/Optimizer'
import Results from './pages/Results'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Landing />} />
        <Route path="/sandbox" element={<Sandbox />} />
        <Route path="/optimizer" element={<Optimizer />} />
        <Route path="/results" element={<Results />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
