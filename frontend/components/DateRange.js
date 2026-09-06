'use client'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
export default function DateRange({ value, onChange }) {
  const {t}=useI18n(); const [from,setFrom]=useState(''),[to,setTo]=useState(''); const selected=value.range||'today'
  const applyCustom=()=>{if(from&&to)onChange({range:'custom',from_date:from,to_date:to})}
  return <div className="date-filter"><select value={selected} onChange={e=>onChange({range:e.target.value})}><option value="today">{t('Today')}</option><option value="yesterday">{t('Yesterday')}</option><option value="last7">{t('Last 7 Days')}</option><option value="last30">{t('Last 30 Days')}</option><option value="this_month">{t('This Month')}</option><option value="last_month">{t('Last Month')}</option><option value="custom">{t('Custom')}</option></select>{selected==='custom'&&<><input type="date" value={from} onChange={e=>setFrom(e.target.value)}/><input type="date" value={to} onChange={e=>setTo(e.target.value)}/><button className="btn secondary" onClick={applyCustom}>{t('Apply')}</button></>}</div>
}
