import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider, createBrowserRouter } from 'react-router-dom'
import './index.css'
import { App } from './App'
import { CancerDetailPage } from './pages/CancerDetailPage'
import { CancerOverviewPage } from './pages/CancerOverviewPage'
import { DetailPage } from './pages/DetailPage'
import { OverviewPage } from './pages/OverviewPage'
import { TargetDetailPage } from './pages/TargetDetailPage'

const router = createBrowserRouter([
  {
    path: '/',
    element: <App />,
    children: [
      { index: true, element: <OverviewPage /> },
      { path: 'drugs/:chemblId', element: <DetailPage /> },
      { path: 'cancers', element: <CancerOverviewPage /> },
      { path: 'cancers/:diseaseId', element: <CancerDetailPage /> },
      { path: 'targets/:ensemblId', element: <TargetDetailPage /> },
    ],
  },
])

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
)
