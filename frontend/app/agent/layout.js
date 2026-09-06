'use client'
import AuthGate from '../../components/AuthGate'
import Shell from '../../components/Shell'
export default function AgentLayout({ children }) {
  return <AuthGate roles={['AGENT']}>{user => <Shell user={user} mode="agent">{children}</Shell>}</AuthGate>
}
