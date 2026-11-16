import React from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Sidebar } from './components/Sidebar'
import { ProcessDrawer } from './components/ProcessDrawer'
import { ActionConfirmationModal } from './components/ActionConfirmationModal'
import {
  Dashboard,
  MonitoringPage,
  ProcessesPage,
  IncidentsPage,
  PolicyPage,
  SettingsPage,
  PredictionsPage,
  MaintenancePage,
  ApplicationManagerPage,
  HibernatorPage,
} from './pages'
import { AskNexusChat } from './components/AskNexusChat'
import { useWebSocket } from './hooks/useWebSocket'
import { useNexusStore } from './store'

function AppContent() {
  // Activate WebSocket connection to backend orchestrator
  useWebSocket()

  const { loadIncidents, loadProcesses, fetchPolicy } = useNexusStore()

  React.useEffect(() => {
    // Initial fetch from SQLite database on application boot
    loadIncidents()
    loadProcesses()
    fetchPolicy()
  }, [loadIncidents, loadProcesses, fetchPolicy])

  return (
    <div className="app-layout">
      <Sidebar />
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/monitoring" element={<MonitoringPage />} />
          <Route path="/applications" element={<ApplicationManagerPage />} />
          <Route path="/processes" element={<ProcessesPage />} />
          <Route path="/incidents" element={<IncidentsPage />} />
          <Route path="/incidents/:id" element={<IncidentsPage />} />
          <Route path="/predictions" element={<PredictionsPage />} />
          <Route path="/maintenance" element={<MaintenancePage />} />
          <Route path="/policy" element={<PolicyPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/hibernator" element={<HibernatorPage />} />
        </Routes>
      </main>

      {/* Global Slide-Over Process Drawer */}
      <ProcessDrawer />

      {/* Global Action Confirmation Modal */}
      <ActionConfirmationModal />

      {/* Ask Nexus AI floating chat widget */}
      <AskNexusChat />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}
