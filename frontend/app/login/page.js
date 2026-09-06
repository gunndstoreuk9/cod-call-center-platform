'use client'
import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '../../lib/api'
import { useI18n } from '../../lib/i18n'
import LanguageSwitch from '../../components/LanguageSwitch'
export default function LoginPage(){const router=useRouter(),{t}=useI18n();const[username,setUsername]=useState(''),[password,setPassword]=useState(''),[error,setError]=useState(''),[loading,setLoading]=useState(false);const submit=async e=>{e.preventDefault();setError('');setLoading(true);try{const user=await api('/auth/login',{method:'POST',body:{username,password}});router.replace(user.role==='AGENT'?'/agent/workspace':'/admin')}catch(err){setError(err.message)}finally{setLoading(false)}};return <div className="login-page"><div className="login-language"><LanguageSwitch/></div><div className="login-layout"><section className="login-brand-panel"><div className="login-logo">
          <img
            src="/codops-logo.png"
            alt="COD OPS"
            style={{
              width: '240px',
              maxWidth: '100%',
              height: '95px',
              objectFit: 'contain',
              objectPosition: 'left center'
            }}
          />
        </div><h2>{t('Operations Console')}</h2><p>{t('Admin & agent operations workspace')}</p><div className="login-metrics"><div><strong>LIVE</strong><span>{t('Delivery sync')}</span></div><div><strong>2×</strong><span>EN / العربية</span></div><div><strong>COD</strong><span>{t('Morocco-ready')}</span></div></div></section><form className="login-card" onSubmit={submit}><span className="login-kicker">{t('SECURE WORKSPACE')}</span><h1>{t('COD Call Center')}</h1><p>{t('Admin & agent operations workspace')}</p>{error&&<div className="error">{error}</div>}<div className="field"><label>{t('Username')}</label><input value={username} onChange={e=>setUsername(e.target.value)} autoComplete="username" required/></div><div className="field"><label>{t('Password')}</label><input type="password" value={password} onChange={e=>setPassword(e.target.value)} autoComplete="current-password" required/></div><button className="btn full login-submit" disabled={loading}>{loading?t('Signing in...'):t('Sign in')}</button><small className="secure-note">{t('Protected admin & agent session')}</small></form></div></div>}
