import * as React from 'react'
import {
  Box,
  Paper,
  Typography,
  IconButton,
  Tooltip,
  Divider,
} from '@mui/material'
import Grid from '@mui/material/Grid' // MUI v7 Grid (no `item`; use `size` on children)
import RefreshIcon from '@mui/icons-material/Refresh'

import './home.css'
import DashboardCard from '../components/DashboardCard'
import { getCounts } from '../api/stats'

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
  actions,
}: {
  title: string
  className?: string
  children?: React.ReactNode
  ariaLabel?: string
  actions?: React.ReactNode
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
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <Typography variant="subtitle1" fontWeight={600}>
            {title}
          </Typography>
          {actions}
        </Box>
        <Divider />
        <Box sx={{ flex: 1, display: 'flex', alignItems: 'stretch', justifyContent: 'center' }}>
          {children ?? (
            <Typography variant="body2" color="text.secondary" sx={{ m: 'auto' }}>
              Placeholder
            </Typography>
          )}
        </Box>
      </Paper>
    </Box>
  )
}

/** Configure resource slugs to match your DRF routes under /api/v1/. */
const DASHBOARD_RESOURCES = [
  { key: 'taxa', label: 'Taxa', slug: 'taxa' },
  { key: 'materials', label: 'Plant Materials', slug: 'materials' },
  { key: 'batches', label: 'Batches', slug: 'batches' },
  { key: 'plants', label: 'Plants', slug: 'plants' },
  { key: 'events', label: 'Events', slug: 'events' },
  { key: 'labels', label: 'Labels', slug: 'labels' },
] as const

type Slug = (typeof DASHBOARD_RESOURCES)[number]['slug']
type DashboardData = Record<Slug, number | null>

export default function Home() {
  const [data, setData] = React.useState<DashboardData | null>(null)
  const [loading, setLoading] = React.useState<boolean>(true)
  const [error, setError] = React.useState<string | null>(null)
  const controllerRef = React.useRef<AbortController | null>(null)

  const load = React.useCallback(async () => {
    if (controllerRef.current) controllerRef.current.abort()
    const ctrl = new AbortController()
    controllerRef.current = ctrl

    setLoading(true)
    setError(null)
    try {
      const slugs = DASHBOARD_RESOURCES.map((r) => r.slug)
      const counts = await getCounts(slugs, { signal: ctrl.signal })
      const mapped = Object.fromEntries(slugs.map((s) => [s, counts[s] ?? null])) as DashboardData
      setData(mapped)
    } catch (e: any) {
      setError(e?.message ?? 'Failed to load dashboard')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
    return () => controllerRef.current?.abort()
  }, [load])

  const isLoading = loading && !data

  return (
    <main className="grid-page">
      <div className="parent" role="grid" aria-label="Home layout grid">
        {/* Side panels preserved */}
        <PanelCard className="div3" title="Left Panel" />

        {/* Centered dashboard in the main panel */}
        <PanelCard
          className="div1"
          title="Nursery Overview"
          actions={
            <Tooltip title="Refresh">
              <IconButton aria-label="Refresh dashboard" onClick={load} size="small">
                <RefreshIcon fontSize="small" />
              </IconButton>
            </Tooltip>
          }
        >
          <Box
            sx={{
              width: '100%',
              maxWidth: 1200, // constrain for nicer reading width
              mx: 'auto',     // center horizontally
              py: 1,
            }}
          >
            <Grid container spacing={2} justifyContent="center">
              {DASHBOARD_RESOURCES.map((r) => {
                const value = data ? data[r.slug] : undefined
                const cardError =
                  error && !isLoading ? error : value === null && !loading ? 'Unavailable' : null

                return (
                  <Grid key={r.key} size={{ xs: 12, sm: 6, md: 4, lg: 4, xl: 2 }}>
                    <DashboardCard
                      title={r.label}
                      value={typeof value === 'number' ? value : undefined}
                      loading={isLoading}
                      error={cardError}
                      onRetry={load}
                      aria-label={`${r.label} count`}
                    />
                  </Grid>
                )
              })}
            </Grid>
          </Box>
        </PanelCard>

        <PanelCard className="div4" title="Right Panel" />
        <PanelCard className="div2" title="Footer" />
      </div>
    </main>
  )
}
