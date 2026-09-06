'use client'
import AuthGate from '../../components/AuthGate'
import Shell from '../../components/Shell'
export default function AdminLayout({ children }) {
  return <AuthGate roles={['OWNER','ADMIN','SUPERVISOR']}>{user => <Shell user={user} mode="admin">{children}</Shell>}</AuthGate>
}
