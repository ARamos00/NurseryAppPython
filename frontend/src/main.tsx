import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'

import { ThemeProvider, CssBaseline } from '@mui/material'
import theme from './theme/muiTheme'
import './theme/fonts.css' // registers 'NIS JTC Win M9'

const root = createRoot(document.getElementById('root')!)
root.render(
  <ThemeProvider theme={theme}>
    <CssBaseline />
    <App />
  </ThemeProvider>,
)

