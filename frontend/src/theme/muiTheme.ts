import { createTheme } from '@mui/material/styles'

/**
 * Material UI v7 theme scaffold.
 * - shape.borderRadius is our "inner" radius
 * - typography.fontFamily uses your custom font with sensible fallbacks
 */
const theme = createTheme({
  shape: {
    borderRadius: 12,
  },
  typography: {
    fontFamily: [
      'NIS JTC Win M9', // defined in fonts.css
      '-apple-system',
      'BlinkMacSystemFont',
      '"Segoe UI"',
      'Roboto',
      '"Helvetica Neue"',
      'Arial',
      '"Noto Sans"',
      'sans-serif',
      '"Apple Color Emoji"',
      '"Segoe UI Emoji"',
      '"Segoe UI Symbol"',
    ].join(', '),
  },
  // palette: { mode: 'light' }, // add dark mode later if desired
})

export default theme
