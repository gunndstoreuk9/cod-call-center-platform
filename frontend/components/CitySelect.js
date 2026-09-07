'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'
import { useI18n } from '../lib/i18n'

let cachedCities = null

export default function CitySelect({
  value = '',
  onChange,
  label = 'City',
  placeholder = 'Type city name...',
  required = true,
  disabled = false
}) {
  const { locale } = useI18n()
  const isAr = locale === 'ar'
  const L = (en, ar) => (isAr ? ar : en)

  const [cities, setCities] = useState(cachedCities || [])
  const [query, setQuery] = useState(value || '')
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(!cachedCities)
  const [error, setError] = useState('')
  const rootRef = useRef(null)

  useEffect(() => {
    setQuery(value || '')
  }, [value])

  useEffect(() => {
    if (cachedCities) return

    let alive = true

    api('/orders/cities')
      .then(data => {
        if (!alive) return
        cachedCities = data.cities || []
        setCities(cachedCities)
      })
      .catch(err => {
        if (!alive) return
        setError(err.message || L('Could not load cities', 'تعذر تحميل المدن'))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })

    return () => {
      alive = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const close = event => {
      if (rootRef.current && !rootRef.current.contains(event.target)) {
        setOpen(false)
        setQuery(value || '')
      }
    }

    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [value])

  const results = useMemo(() => {
    const q = query.trim().toLocaleLowerCase()
    const rows = q
      ? cities.filter(city => city.toLocaleLowerCase().includes(q))
      : cities

    return rows.slice(0, 80)
  }, [cities, query])

  const type = event => {
    setQuery(event.target.value)
    onChange('')
    setOpen(true)
  }

  const selectCity = city => {
    setQuery(city)
    onChange(city)
    setOpen(false)
  }

  return (
    <div className="field city-select-field" ref={rootRef}>
      <label>{label}</label>

      <div className="city-select">
        <input
          type="text"
          autoComplete="off"
          required={required}
          disabled={disabled}
          value={query}
          placeholder={loading ? L('Loading cities...', 'جاري تحميل المدن...') : placeholder}
          onFocus={() => !disabled && setOpen(true)}
          onChange={type}
        />

        {value && <span className="city-selected-mark">✓</span>}

        {open && !loading && !disabled && (
          <div className="city-dropdown">
            {error ? (
              <div className="city-empty">{error}</div>
            ) : results.length ? (
              results.map(city => (
                <button
                  type="button"
                  key={city}
                  className={city === value ? 'city-option selected' : 'city-option'}
                  onMouseDown={event => event.preventDefault()}
                  onClick={() => selectCity(city)}
                >
                  {city}
                </button>
              ))
            ) : (
              <div className="city-empty">
                {L('No matching Digylog city', 'لا توجد مدينة مطابقة في Digylog')}
              </div>
            )}
          </div>
        )}
      </div>

      {!value && query && !disabled && (
        <small className="city-help">
          {L(
            'Select a city from the Digylog list.',
            'اختر مدينة من قائمة Digylog.'
          )}
        </small>
      )}
    </div>
  )
}

