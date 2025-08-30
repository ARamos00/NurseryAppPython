import * as React from 'react'
import {
  AppBar,
  Toolbar,
  Typography,
  IconButton,
  Menu,
  MenuItem,
  Box,
  Button,
  Container,
} from '@mui/material'
import MenuIcon from '@mui/icons-material/Menu'
import { Link as RouterLink } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import LogoutButton from '../auth/LogoutButton'

/**
 * Material UI NavBar (AppBar + Toolbar)
 * - Desktop: inline nav buttons
 * - Mobile: hamburger -> Menu with the same links
 * - Router integration via the `component` prop on Button / Typography
 *   per MUI routing integrations docs.
 */
export default function NavBar() {
  const { user } = useAuth()

  const [anchorElNav, setAnchorElNav] = React.useState<null | HTMLElement>(null)

  const openNavMenu = (event: React.MouseEvent<HTMLElement>) => {
    setAnchorElNav(event.currentTarget)
  }
  const closeNavMenu = () => setAnchorElNav(null)

  const pages = [
    { label: 'Home', to: '/' },
    { label: 'Password', to: '/settings/password' },
  ] as const

  return (
    <AppBar position="static" color="default" elevation={0}>
      <Container maxWidth="lg">
        <Toolbar disableGutters sx={{ gap: 1 }}>
          {/* Brand (desktop & mobile) */}
          <Typography
            variant="h6"
            noWrap
            component={RouterLink}
            to="/"
            sx={{
              textDecoration: 'none',
              color: 'text.primary',
              fontWeight: 700,
              mr: 2,
            }}
          >
            Nursery&nbsp;Tracker
          </Typography>

          {/* Mobile menu button */}
          <Box sx={{ display: { xs: 'flex', md: 'none' }, ml: 'auto' }}>
            <IconButton
              size="large"
              aria-label="open navigation menu"
              aria-controls="nav-menu"
              aria-haspopup="true"
              onClick={openNavMenu}
              edge="end"
            >
              <MenuIcon />
            </IconButton>
            <Menu
              id="nav-menu"
              anchorEl={anchorElNav}
              open={Boolean(anchorElNav)}
              onClose={closeNavMenu}
              keepMounted
              anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
              transformOrigin={{ vertical: 'top', horizontal: 'right' }}
            >
              {pages.map((p) => (
                <MenuItem
                  key={p.to}
                  component={RouterLink}
                  to={p.to}
                  onClick={closeNavMenu}
                >
                  {p.label}
                </MenuItem>
              ))}
              {user && (
                <MenuItem onClick={closeNavMenu} disableRipple>
                  <Box sx={{ pl: 0.5 }}>
                    <LogoutButton />
                  </Box>
                </MenuItem>
              )}
            </Menu>
          </Box>

          {/* Desktop nav links + user actions */}
          <Box
            sx={{
              display: { xs: 'none', md: 'flex' },
              alignItems: 'center',
              gap: 1,
              ml: 'auto',
            }}
          >
            {pages.map((p) => (
              <Button
                key={p.to}
                component={RouterLink}
                to={p.to}
                color="inherit"
                sx={{ textTransform: 'none', fontWeight: 600 }}
              >
                {p.label}
              </Button>
            ))}
            {user && (
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  pl: 1,
                  borderLeft: (t) => `1px solid ${t.palette.divider}`,
                }}
              >
                <Typography
                  variant="body2"
                  sx={{ color: 'text.secondary' }}
                  title={user.email}
                  aria-live="polite"
                >
                  {user.username}
                </Typography>
                <LogoutButton />
              </Box>
            )}
          </Box>
        </Toolbar>
      </Container>
    </AppBar>
  )
}
