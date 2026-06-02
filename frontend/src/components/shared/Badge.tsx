import React from 'react'

interface BadgeProps {
  children: React.ReactNode
  variant?: 'green' | 'red' | 'amber' | 'blue' | 'neutral'
  className?: string
}

export default function Badge({ children, variant = 'blue', className = '' }: BadgeProps) {
  const variantClasses = {
    green: 'badge-green',
    red: 'badge-red',
    amber: 'badge-amber',
    blue: 'badge-blue',
    neutral: 'bg-gray-800 text-gray-400',
  }

  return (
    <span className={`badge ${variantClasses[variant]} ${className}`}>
      {children}
    </span>
  )
}
