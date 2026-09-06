'use client'
import { useEffect,useState } from 'react'
import { useRouter } from 'next/navigation'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'
export default function AuthGate({roles,children}){const router=useRouter(),[user,setUser]=useState(null),[loading,setLoading]=useState(true);const {t}=useI18n();useEffect(()=>{api('/auth/me').then(me=>{if(roles&&!roles.includes(me.role)){router.replace(me.role==='AGENT'?'/agent/workspace':'/login');return}setUser(me)}).catch(()=>router.replace('/login')).finally(()=>setLoading(false))},[router]);if(loading)return <div className="center-screen"><div className="loader"/><strong>{t('Loading...')}</strong></div>;if(!user)return null;return children(user)}
