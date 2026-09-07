import './globals.css'

import { LanguageProvider } from '../lib/i18n'

export const metadata = {
  title: 'COD Operations | Call Center',
  description: 'Bilingual multi-product COD call center operations platform'
}

export default function RootLayout({ children }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+Arabic:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
      </head>

      <body>
        <LanguageProvider>{children}</LanguageProvider>
      </body>
    </html>
  )
}
