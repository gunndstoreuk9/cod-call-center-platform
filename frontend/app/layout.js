import './globals.css'
import { LanguageProvider } from '../lib/i18n'

export const metadata = {
  title: 'COD Operations | Call Center',
  description: 'Bilingual multi-product COD call center operations platform'
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body><LanguageProvider>{children}</LanguageProvider></body>
    </html>
  )
}
