import * as React from 'react'
import { Card, CardContent, Typography, Box, Button, Alert, Skeleton } from '@mui/material'

export type DashboardCardProps = {
  title: string
  value?: number | null
  loading?: boolean
  error?: string | null
  onRetry?: () => void
  icon?: React.ReactNode
  'aria-label'?: string
}

export default function DashboardCard(props: DashboardCardProps) {
  const { title, value, loading = false, error = null, onRetry, icon } = props

  return (
    <Card variant="outlined" aria-label={props['aria-label'] ?? title} sx={{ height: '100%' }}>
      <CardContent sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, height: '100%' }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1 }}>
          <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
            {title}
          </Typography>
          {icon ? <Box sx={{ display: 'inline-flex' }}>{icon}</Box> : null}
        </Box>

        <Box sx={{ flex: 1, display: 'flex', alignItems: 'center' }}>
          {loading ? (
            <Skeleton variant="rounded" width={96} height={40} />
          ) : error ? (
            <Alert severity="error" sx={{ width: '100%' }}>
              {error}
            </Alert>
          ) : (
            <Typography variant="h3" component="p" sx={{ lineHeight: 1.1 }}>
              {value ?? '—'}
            </Typography>
          )}
        </Box>

        {error && onRetry ? (
          <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
            <Button size="small" onClick={onRetry} variant="outlined">
              Retry
            </Button>
          </Box>
        ) : null}
      </CardContent>
    </Card>
  )
}
