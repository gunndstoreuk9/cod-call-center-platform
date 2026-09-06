'use client'
import { useI18n } from '../lib/i18n'
export default function LanguageSwitch({ compact=false }) {
  const { locale, setLocale } = useI18n()
  return <div className={compact?'language-switch compact':'language-switch'} aria-label="Language">
    <button type="button" className={locale==='en'?'active':''} onClick={()=>setLocale('en')}>EN</button>
    <button type="button" className={locale==='ar'?'active':''} onClick={()=>setLocale('ar')}>ع</button>
  </div>
}
