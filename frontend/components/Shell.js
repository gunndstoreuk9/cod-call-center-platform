'use client'
import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
import LanguageSwitch from './LanguageSwitch'
import Icon from './Icon'

const adminLinks = [
  ['/admin', 'Dashboard','dashboard'],
  ['/admin/orders', 'Orders','orders'],
  ['/admin/products', 'Products','products'],
  ['/admin/stores', 'Stores','stores'],
  ['/admin/agents', 'Agents','agents'],
  ['/admin/payments', 'Payments','payments'],
  ['/admin/callbacks', 'Callbacks','callbacks'],
  ['/admin/integrations', 'Integrations','integrations'],
  ['/admin/delivery', 'Live Delivery','delivery']
]
const agentLinks = [
  ['/agent/workspace', 'Workspace','workspace'],
  ['/agent/stats', 'My Stats','stats']
]

export default function Shell({ user, mode, children }) {
  const pathname = usePathname(); const router = useRouter(); const {t}=useI18n()
  const links = mode === 'agent' ? agentLinks : adminLinks
  const current = links.find(([href])=>href===pathname) || links[0]
  const logout = async () => { try { await api('/auth/logout', { method: 'POST' }) } catch (_) {} router.replace('/login') }
  const initials=(user.display_name||'CC').split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase()
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-wrap">
          <img
            src="/codops-logo.png"
            alt="COD OPS"
            style={{
              width: '170px',
              maxWidth: '100%',
              height: '64px',
              objectFit: 'contain',
              objectPosition: 'left center'
            }}
          />
        </div>
        <div className="nav-caption">{mode==='agent'?t('Workspace'):t('Operations Console')}</div>
        <nav>
          {links.map(([href,label,icon]) => <Link key={href} href={href} className={pathname === href ? 'nav-link active' : 'nav-link'}><span className="nav-icon"><Icon name={icon}/></span><span>{t(label)}</span></Link>)}
        </nav>
        <div className="sidebar-user">
          <div className="avatar">{initials}</div><div className="user-copy"><strong>{user.display_name}</strong><small>{user.role}</small></div>
          <button className="logout-icon" onClick={logout} title={t('Logout')}><Icon name="logout"/></button>
        </div>
      </aside>
      <div className="content-shell">
        <header className="topbar"><div><span className="eyebrow">COD OPERATIONS</span><strong>{t(current?.[1]||'Dashboard')}</strong></div><div className="topbar-actions"><LanguageSwitch/><div className="top-user"><span className="online-dot"/><span>{user.display_name}</span></div></div></header>
        <main className="main">{children}</main>
      </div>
    </div>
  )
}
