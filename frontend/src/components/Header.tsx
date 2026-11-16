import React from 'react'
import { PageTopbar } from './PageTopbar'

interface HeaderProps {
  title: string
  description?: string
  actions?: React.ReactNode
}

export function Header({ title }: HeaderProps) {
  return <PageTopbar current={title} />
}
