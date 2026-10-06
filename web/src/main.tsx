import '@fontsource/overpass/400.css'
import '@fontsource/overpass/600.css'
import '@fontsource/overpass/700.css'
import '@fontsource/overpass/800.css'
import './styles.css'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
