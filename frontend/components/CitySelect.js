'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../lib/api'

let cachedCities = null

export default function CitySelect({
  value = '',
  onChange,
  label = 'City',
  placeholder = 'Type city name...'
}) {
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
        setError(err.message || 'Could not load cities')
      })
      .finally(() => {
        if (alive) setLoading(false)
      })

    return () => {
      alive = false
    }
  }, [])

  useEffect(() => {
    const close = e => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setOpen(false)

        if (!value) {
          setQuery('')
        } else {
          setQuery(value)
        }
      }
    }

    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [value])

  const results = useMemo(() => {
    const q = query.trim().toLocaleLowerCase()

    const rows = q
      ? cities.filter(city =>
          city.toLocaleLowerCase().includes(q)
        )
      : cities

    return rows.slice(0, 80)
  }, [cities, query])

  const type = e => {
    setQuery(e.target.value)

    // Typing is only search. It is NOT a valid city selection.
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
          required
          value={query}
          placeholder={loading ? 'Loading cities...' : placeholder}
          onFocus={() => setOpen(true)}
          onChange={type}
        />

        {value && (
          <span className="city-selected-mark">✓</span>
        )}

        {open && !loading && (
          <div className="city-dropdown">
            {error ? (
              <div className="city-empty">{error}</div>
            ) : results.length ? (
              results.map(city => (
                <button
                  type="button"
                  key={city}
                  className={
                    city === value
                      ? 'city-option selected'
                      : 'city-option'
                  }
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => selectCity(city)}
                >
                  {city}
                </button>
              ))
            ) : (
              <div className="city-empty">
                No matching Digylog city
              </div>
            )}
          </div>
        )}
      </div>

      {!value && query && (
        <small className="city-help">
          Select a city from the Digylog list.
        </small>
      )}
    </div>
  )
}
