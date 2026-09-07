'use client'

import { useEffect, useState } from 'react'
import { api, money } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import DateRange from '../../../components/DateRange'
import StatCard from '../../../components/StatCard'
import StatusBadge from '../../../components/StatusBadge'

const PAGE_SIZE = 10

function query(period) {
  const p = new URLSearchParams()

  p.set('range', period.range || 'today')

  if (period.from_date) {
    p.set('from_date', period.from_date)
  }

  if (period.to_date) {
    p.set('to_date', period.to_date)
  }

  return p.toString()
}

function pageItems(current, totalPages) {
  if (totalPages <= 7) {
    return Array.from(
      { length: totalPages },
      (_, i) => i + 1
    )
  }

  const items = [1]

  let start = Math.max(2, current - 1)
  let end = Math.min(
    totalPages - 1,
    current + 1
  )

  if (current <= 3) {
    end = 4
  }

  if (current >= totalPages - 2) {
    start = totalPages - 3
  }

  if (start > 2) {
    items.push('left-dots')
  }

  for (let i = start; i <= end; i++) {
    items.push(i)
  }

  if (end < totalPages - 1) {
    items.push('right-dots')
  }

  items.push(totalPages)

  return items
}

function Pagination({
  page,
  total,
  pageSize,
  onChange
}) {
  const totalPages = Math.max(
    1,
    Math.ceil(total / pageSize)
  )

  if (!total) {
    return null
  }

  const first =
    (page - 1) * pageSize + 1

  const last = Math.min(
    page * pageSize,
    total
  )

  return (
    <div className="delivery-pagination">
      <div className="delivery-pagination-info">
        {first}–{last} / {total}
      </div>

      <div className="delivery-pagination-buttons">

        <button
          type="button"
          className="delivery-page-btn"
          disabled={page <= 1}
          onClick={() =>
            onChange(
              Math.max(1, page - 1)
            )
          }
          aria-label="Previous page"
        >
          ‹
        </button>

        {pageItems(
          page,
          totalPages
        ).map(item => {
          if (
            item === 'left-dots' ||
            item === 'right-dots'
          ) {
            return (
              <span
                className="delivery-page-dots"
                key={item}
              >
                …
              </span>
            )
          }

          return (
            <button
              type="button"
              key={item}
              className={
                'delivery-page-number' +
                (item === page
                  ? ' active'
                  : '')
              }
              onClick={() =>
                onChange(item)
              }
            >
              {item}
            </button>
          )
        })}

        <button
          type="button"
          className="delivery-page-btn"
          disabled={page >= totalPages}
          onClick={() =>
            onChange(
              Math.min(
                totalPages,
                page + 1
              )
            )
          }
          aria-label="Next page"
        >
          ›
        </button>

      </div>
    </div>
  )
}

export default function DeliveryPage() {
  const { t, date } = useI18n()

  const [period, setPeriod] =
    useState({
      range: 'today'
    })

  const [data, setData] =
    useState(null)

  const [health, setHealth] =
    useState(null)

  const [error, setError] =
    useState('')

  const [
    shipments,
    setShipments
  ] = useState([])

  const [
    shipmentPage,
    setShipmentPage
  ] = useState(1)

  const [
    shipmentTotal,
    setShipmentTotal
  ] = useState(0)

  const [
    events,
    setEvents
  ] = useState([])

  const [
    eventPage,
    setEventPage
  ] = useState(1)

  const [
    eventTotal,
    setEventTotal
  ] = useState(0)


  const loadDashboard = async () => {
    try {
      const [d, h] =
        await Promise.all([
          api(
            `/delivery/dashboard?${query(period)}`
          ),
          api('/delivery/health')
        ])

      setData(d)
      setHealth(h)
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }


  const loadShipments = async (
    page = shipmentPage
  ) => {
    try {
      const offset =
        (page - 1) * PAGE_SIZE

      const response = await api(
        `/delivery/shipments` +
        `?limit=${PAGE_SIZE}` +
        `&offset=${offset}` +
        `&paginated=true`
      )

      setShipments(
        response.items || []
      )

      setShipmentTotal(
        response.total || 0
      )

      setError('')
    } catch (e) {
      setError(e.message)
    }
  }


  const loadEvents = async (
    page = eventPage
  ) => {
    try {
      const offset =
        (page - 1) * PAGE_SIZE

      const response = await api(
        `/delivery/events` +
        `?limit=${PAGE_SIZE}` +
        `&offset=${offset}` +
        `&paginated=true`
      )

      setEvents(
        response.items || []
      )

      setEventTotal(
        response.total || 0
      )

      setError('')
    } catch (e) {
      setError(e.message)
    }
  }


  useEffect(() => {
    loadDashboard()
  }, [period])


  useEffect(() => {
    loadShipments(shipmentPage)
  }, [shipmentPage])


  useEffect(() => {
    loadEvents(eventPage)
  }, [eventPage])


  const seed = async () => {
    try {
      await api(
        '/delivery/status-mappings/seed-digylog',
        {
          method: 'POST'
        }
      )

      await Promise.all([
        loadDashboard(),
        loadShipments(),
        loadEvents()
      ])
    } catch (e) {
      setError(e.message)
    }
  }


  return (
    <>
      <div className="page-head">
        <div>
          <h1>
            {t('Live Delivery')}
          </h1>

          <p>
            {t(
              'Digylog shipments, webhook statuses and delivery rates.'
            )}
          </p>
        </div>

        <DateRange
          value={period}
          onChange={setPeriod}
        />
      </div>


      {error && (
        <div className="error">
          {error}
        </div>
      )}


      {health && (
        <div className="panel">

          <div className="panel-head">
            <div>
              <h2>
                {t('Digylog health')}
              </h2>

              <p>
                {health.connected
                  ? t('Connected')
                  : t('Not connected')}

                {' · '}

                {t('Last webhook:')}{' '}

                {health.last_webhook_at
                  ? date(
                      health.last_webhook_at
                    )
                  : '—'}
              </p>
            </div>

            <button
              className="btn secondary"
              onClick={seed}
            >
              {t(
                'Seed Status Mappings'
              )}
            </button>
          </div>


          <div className="stats-grid">

            <StatCard
              label={t(
                'Failed shipments'
              )}
              value={
                health.failed_shipments ||
                0
              }
              tone="danger"
            />

            <StatCard
              label={t(
                'Unmatched events'
              )}
              value={
                health.unmatched_events ||
                0
              }
              tone="warning"
            />

            <StatCard
              label={t('Last test')}
              value={
                health.last_test_status ||
                '—'
              }
            />

            <StatCard
              label={t('Last sync')}
              value={
                health.last_sync_status ||
                '—'
              }
            />

          </div>
        </div>
      )}


      {data && (
        <>
          <div className="stats-grid">

            <StatCard
              label={t('Confirmed')}
              value={data.confirmed}
              tone="brand"
            />

            <StatCard
              label={t(
                'Sent to delivery'
              )}
              value={data.sent}
              note={`${data.dispatch_rate}%`}
              tone="brand"
            />

            <StatCard
              label={t('In delivery')}
              value={data.in_delivery}
              tone="warning"
            />

            <StatCard
              label={t('Delivered')}
              value={data.delivered}
              note={`${data.confirmed_to_delivered_rate}% ${t('of confirmed')}`}
              tone="success"
            />

            <StatCard
              label={t('Refused')}
              value={data.refused}
              note={`${data.refusal_rate}%`}
              tone="danger"
            />

            <StatCard
              label={t('Returned')}
              value={data.returned}
              note={`${data.return_rate}%`}
              tone="warning"
            />

            <StatCard
              label={t('Issues')}
              value={data.issues}
              tone="danger"
            />

            <StatCard
              label={t(
                'Delivered revenue'
              )}
              value={money(
                data.delivered_revenue
              )}
              tone="success"
            />

          </div>


          <div className="panel">
            <div className="panel-head">
              <h2>
                {t(
                  'Product delivery performance'
                )}
              </h2>
            </div>

            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>
                      {t('Product')}
                    </th>

                    <th>
                      {t('Confirmed')}
                    </th>

                    <th>
                      {t('Sent')}
                    </th>

                    <th>
                      {t('Delivered')}
                    </th>

                    <th>
                      {t('Refused')}
                    </th>

                    <th>
                      {t('Returned')}
                    </th>

                    <th>
                      {t('Dispatch %')}
                    </th>

                    <th>
                      {t(
                        'Confirmed → Delivered'
                      )}
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {data.products.map(
                    p => (
                      <tr
                        key={
                          p.product_id
                        }
                      >
                        <td>
                          <strong>
                            {p.product}
                          </strong>

                          <br />

                          <small>
                            {p.sku}
                          </small>
                        </td>

                        <td>
                          {p.confirmed}
                        </td>

                        <td>
                          {p.sent}
                        </td>

                        <td>
                          {p.delivered}
                        </td>

                        <td>
                          {p.refused}
                        </td>

                        <td>
                          {p.returned}
                        </td>

                        <td>
                          {p.dispatch_rate}%
                        </td>

                        <td>
                          {
                            p.confirmed_to_delivered_rate
                          }
                          %
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          </div>


          <div className="panel">
            <div className="panel-head">
              <h2>
                {t(
                  'Agent delivery quality'
                )}
              </h2>
            </div>

            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>
                      {t('Agent')}
                    </th>

                    <th>
                      {t('Confirmed')}
                    </th>

                    <th>
                      {t('Sent')}
                    </th>

                    <th>
                      {t('Delivered')}
                    </th>

                    <th>
                      {t('Refused')}
                    </th>

                    <th>
                      {t('Dispatch %')}
                    </th>

                    <th>
                      {t(
                        'Confirmed → Delivered'
                      )}
                    </th>

                    <th>
                      {t('Refusal %')}
                    </th>
                  </tr>
                </thead>

                <tbody>
                  {data.agents.map(
                    a => (
                      <tr
                        key={
                          a.agent_id
                        }
                      >
                        <td>
                          <strong>
                            {a.agent}
                          </strong>
                        </td>

                        <td>
                          {a.confirmed}
                        </td>

                        <td>
                          {a.sent}
                        </td>

                        <td>
                          {a.delivered}
                        </td>

                        <td>
                          {a.refused}
                        </td>

                        <td>
                          {a.dispatch_rate}%
                        </td>

                        <td>
                          {
                            a.confirmed_to_delivered_rate
                          }
                          %
                        </td>

                        <td>
                          {a.refusal_rate}%
                        </td>
                      </tr>
                    )
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}


      {/* LATEST SHIPMENTS */}
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>
              {t('Latest shipments')}
            </h2>

            <p>
              {shipmentTotal}{' '}
              {t('shipments')}
            </p>
          </div>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>
                  {t('Tracking')}
                </th>

                <th>
                  {t('Status')}
                </th>

                <th>
                  {t(
                    'External status'
                  )}
                </th>

                <th>
                  {t('City')}
                </th>

                <th>
                  {t('Fee')}
                </th>

                <th>
                  {t('Last sync')}
                </th>
              </tr>
            </thead>

            <tbody>
              {shipments.map(s => (
                <tr key={s.id}>
                  <td>
                    {s.tracking_number ||
                      s.external_id ||
                      '—'}
                  </td>

                  <td>
                    <StatusBadge
                      value={s.status}
                    />
                  </td>

                  <td>
                    {s.external_status_id ??
                      '—'}{' '}
                    {s.external_status_name ||
                      ''}
                  </td>

                  <td>
                    {s.destination_city ||
                      '—'}
                  </td>

                  <td>
                    {s.delivery_fee
                      ? money(
                          s.delivery_fee
                        )
                      : '—'}
                  </td>

                  <td>
                    {s.last_synced_at
                      ? date(
                          s.last_synced_at
                        )
                      : '—'}
                  </td>
                </tr>
              ))}

              {shipments.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty">
                      —
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          page={shipmentPage}
          total={shipmentTotal}
          pageSize={PAGE_SIZE}
          onChange={setShipmentPage}
        />
      </div>


      {/* LATEST DELIVERY EVENTS */}
      <div className="panel">
        <div className="panel-head">
          <div>
            <h2>
              {t(
                'Latest delivery events'
              )}
            </h2>

            <p>
              {eventTotal}{' '}
              {t('events')}
            </p>
          </div>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>
                  {t('Time')}
                </th>

                <th>
                  {t('Event')}
                </th>

                <th>
                  {t('Order')}
                </th>

                <th>
                  {t('Tracking')}
                </th>

                <th>
                  {t(
                    'External status'
                  )}
                </th>

                <th>
                  {t(
                    'Internal status'
                  )}
                </th>

                <th>
                  {t('Matched')}
                </th>
              </tr>
            </thead>

            <tbody>
              {events.map(e => (
                <tr key={e.id}>
                  <td>
                    {date(
                      e.received_at
                    )}
                  </td>

                  <td>
                    {e.event_type}
                  </td>

                  <td>
                    {e.external_order_number ||
                      '—'}
                  </td>

                  <td>
                    {e.tracking_number ||
                      '—'}
                  </td>

                  <td>
                    {e.external_status_id ??
                      '—'}
                  </td>

                  <td>
                    <StatusBadge
                      value={
                        e.internal_status ||
                        '—'
                      }
                    />
                  </td>

                  <td>
                    <StatusBadge
                      value={
                        e.matched
                          ? 'SUCCESS'
                          : 'FAILED'
                      }
                    />
                  </td>
                </tr>
              ))}

              {events.length === 0 && (
                <tr>
                  <td colSpan="7">
                    <div className="empty">
                      —
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        <Pagination
          page={eventPage}
          total={eventTotal}
          pageSize={PAGE_SIZE}
          onChange={setEventPage}
        />
      </div>
    </>
  )
}
