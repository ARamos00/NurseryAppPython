import * as React from 'react'
import { Box, Paper, Typography } from '@mui/material'
import './home.css'

/**
 * PanelCard
 * Outer Box: wireframe container whose borderRadius = innerRadius + padding
 * Inner Paper: outlined panel using theme.shape.borderRadius
 */
function PanelCard({
  title,
  className,
  children,
  ariaLabel,
}: {
  title: string
  className?: string
  children?: React.ReactNode
  ariaLabel?: string
}) {
  return (
    <Box
      className={className}
      aria-label={ariaLabel ?? title}
      sx={(t) => ({
        p: 2,
        border: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.default',
        borderRadius: `calc(${t.shape.borderRadius}px + ${t.spacing(2)})`,
      })}
    >
      <Paper
        variant="outlined"
        sx={(t) => ({
          p: 2,
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          gap: 1,
          borderRadius: t.shape.borderRadius,
          bgcolor: 'background.paper',
        })}
      >
        <Typography variant="subtitle1" fontWeight={600}>
          {title}
        </Typography>
        <Box sx={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          {children ?? (
            <Typography variant="body2" color="text.secondary">
              Placeholder
            </Typography>
          )}
        </Box>
      </Paper>
    </Box>
  )
}

export default function Home() {
  return (
    <main className="grid-page">
      <div className="parent" role="grid" aria-label="Home layout grid">
        {/* Updated four-area layout (no nav content in page) */}
        <PanelCard className="div3" title="Left Panel" />
        <PanelCard className="div1" title="Main Panel" />
        <PanelCard className="div4" title="Right Panel" />
        <PanelCard className="div2" title="Footer" />
      </div>
    </main>
  )
}
