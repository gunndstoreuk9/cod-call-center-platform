export default function Icon({ name, size=18 }) {
  const paths = {
    dashboard:'M3 3h7v7H3z M14 3h7v4h-7z M14 11h7v10h-7z M3 14h7v7H3z',
    orders:'M6 3h12v18H6z M9 7h6 M9 11h6 M9 15h4',
    products:'M4 7l8-4 8 4-8 4z M4 7v10l8 4 8-4V7 M12 11v10',
    stores:'M3 9l2-6h14l2 6 M5 9v12h14V9 M9 21v-7h6v7',
    agents:'M16 21v-2a4 4 0 00-4-4H6a4 4 0 00-4 4v2 M9 11a4 4 0 100-8 4 4 0 000 8z M22 21v-2a4 4 0 00-3-3.87 M16 3.13a4 4 0 010 7.75',
    payments:'M12 1v22 M17 5H9.5a3.5 3.5 0 000 7H14a3.5 3.5 0 010 7H6',
    callbacks:'M21 15a4 4 0 01-4 4H8l-5 3V7a4 4 0 014-4h10a4 4 0 014 4z M8 8h8 M8 12h5',
    integrations:'M8 12h8 M12 8v8 M4 4l4 4 M20 4l-4 4 M4 20l4-4 M20 20l-4-4',
    delivery:'M3 6h11v10H3z M14 9h4l3 3v4h-7z M7 20a2 2 0 100-4 2 2 0 000 4z M19 20a2 2 0 100-4 2 2 0 000 4z',
    workspace:'M4 4h16v12H5.5L4 17.5z M8 8h8 M8 12h5',
    stats:'M4 20V10 M10 20V4 M16 20v-7 M22 20H2',
    logout:'M10 17l5-5-5-5 M15 12H3 M21 19V5a2 2 0 00-2-2h-6',
    globe:'M12 22a10 10 0 100-20 10 10 0 000 20z M2 12h20 M12 2a15.3 15.3 0 010 20 M12 2a15.3 15.3 0 000 20'
  }
  return <svg className="ui-icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]||paths.dashboard}/></svg>
}
