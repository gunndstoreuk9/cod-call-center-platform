'use client'
import { useI18n } from '../lib/i18n'
const ok = ['ACTIVE','SUCCESS','CONFIRMED','DELIVERED','PAID','CONNECTED']
const bad = ['FAILED','CANCELLED','REFUSED','WRONG_NUMBER','INACTIVE','DISABLED','DELIVERY_ISSUE']
const warn = ['PENDING','CALLBACK','FOLLOW_UP','NO_ANSWER','BUSY','RETURNED','UNPAID','NOT_TESTED','NOT READY','NOT_READY']
export default function StatusBadge({ value, className='' }) {
 const { status } = useI18n(); const v=String(value||'—').toUpperCase(); const tone=ok.includes(v)?'ok':bad.includes(v)?'bad':warn.includes(v)?'warn':''
 return <span className={`badge ${tone} ${className}`.trim()}><i className="status-dot"/>{status(value||'—')}</span>
}
