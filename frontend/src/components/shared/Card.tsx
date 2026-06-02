import React from 'react'

interface CardProps {
  children: React.ReactNode
  className?: string
  title?: string
}

export default function Card({ children, className = '', title }: CardProps) {
  return (
    <div className={`card ${className}`}>
      {title && (
        <h3 className="text-sm font-semibold uppercase tracking-wide text-energy-text-secondary mb-md">
          {title}
        </h3>
      )}
      {children}
    </div>
  )
}
