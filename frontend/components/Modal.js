'use client'
import { useI18n } from '../lib/i18n'
export default function Modal({open,title,onClose,children,wide=false}){const {t}=useI18n();if(!open)return null;return <div className="modal-backdrop" onMouseDown={onClose}><div className={wide?'modal wide':'modal'} onMouseDown={e=>e.stopPropagation()}><div className="modal-head"><div><span className="modal-kicker">COD OPS</span><h3>{t(title)}</h3></div><button className="icon-btn" onClick={onClose} aria-label={t('Close')}>×</button></div>{children}</div></div>}
