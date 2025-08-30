import React from 'react'
import './home.css'

/**
 * Simple structural box with an outer container and an inner panel.
 * The CSS ensures: outerRadius = innerRadius + padding (see home.css).
 */
function Box({
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
    <section className={`card ${className ?? ''}`} aria-label={ariaLabel ?? title}>
      <div className="card__inner">
        <header className="card__header">
          <h2 className="card__title">{title}</h2>
        </header>
        <div className="card__body">
          {children ?? <p className="muted">Placeholder</p>}
        </div>
      </div>
    </section>
  )
}

export default function Home() {
  return (
    <main className="grid-page">
      <div className="parent" role="grid" aria-label="Home layout grid">
        {/* New layout (no nav content inside the page) */}
        <Box className="div3" title="Left Panel" />
        <Box className="div1" title="Main Panel" />
        <Box className="div4" title="Right Panel" />
        <Box className="div2" title="Footer" />
      </div>
    </main>
  )
}
