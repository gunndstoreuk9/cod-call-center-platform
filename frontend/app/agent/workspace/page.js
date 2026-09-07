'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, money } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import Modal from '../../../components/Modal'
import StatusBadge from '../../../components/StatusBadge'
import CitySelect from '../../../components/CitySelect'

const emptyManual = {
  product_id: '',
  offer_id: '',
  customer_name: '',
  phone: '',
  city: '',
  address: '',
  quantity: 1,
  call_note: ''
}

const blockedDelivery = [
  'DISPATCHED',
  'IN_TRANSIT',
  'OUT_FOR_DELIVERY',
  'DELIVERED'
]

export default function WorkspacePage() {
  const { t, status: statusText, date } = useI18n()

  const [bucket, setBucket] = useState('NEW')
  const [orders, setOrders] = useState([])
  const [allOrders, setAllOrders] = useState([])
  const [search, setSearch] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')

  const [selectedIds, setSelectedIds] = useState([])
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkResult, setBulkResult] = useState(null)
  const [dispatchingId, setDispatchingId] = useState(null)

  const [selected, setSelected] = useState(null)

  const [cbOpen, setCbOpen] = useState(false)
  const [cbTime, setCbTime] = useState('')
  const [cbNote, setCbNote] = useState('')

  const [manualOpen, setManualOpen] = useState(false)
  const [products, setProducts] = useState([])
  const [manual, setManual] = useState(emptyManual)
  const [savingManual, setSavingManual] = useState(false)

  const [editOpen, setEditOpen] = useState(false)
  const [savingEdit, setSavingEdit] = useState(false)
  const [editForm, setEditForm] = useState({
    customer_name: '',
    phone: '',
    city: '',
    address: '',
    quantity: 1,
    unit_price: '',
    total_price: '',
    call_note: ''
  })

  const isReady = o =>
    o?.call_status === 'CONFIRMED' &&
    !blockedDelivery.includes(o?.delivery_status)

  const isSent = o =>
    blockedDelivery.includes(o?.delivery_status)

  const fetchData = async activeBucket => {
    setError('')

    try {
      const apiBucket = activeBucket === 'READY' ? 'ALL' : activeBucket

      const [rows, summary] = await Promise.all([
        api(`/orders/my-queue?bucket=${apiBucket}&limit=200`),
        api('/orders/my-queue?bucket=ALL&limit=200')
      ])

      const visible =
        activeBucket === 'READY'
          ? rows.filter(isReady)
          : rows

      setOrders(visible)
      setAllOrders(summary)

      setSelectedIds(current =>
        current.filter(id =>
          visible.some(o => o.id === id && isReady(o))
        )
      )
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    fetchData(bucket)
  }, [bucket])

  const refresh = async () => {
    await fetchData(bucket)
  }

  const counts = useMemo(() => {
    const followUp = allOrders.filter(o =>
      ['NO_ANSWER', 'BUSY', 'CALLBACK'].includes(o.call_status)
    ).length

    return {
      all: allOrders.length,
      new: allOrders.filter(o => o.call_status === 'NEW').length,
      followUp,
      confirmed: allOrders.filter(o => o.call_status === 'CONFIRMED').length,
      ready: allOrders.filter(isReady).length,
      sent: allOrders.filter(isSent).length,
      blacklist: allOrders.filter(o => o.call_status === 'BLACKLIST').length
    }
  }, [allOrders])

  const filteredOrders = useMemo(() => {
    const q = search.trim().toLowerCase()

    if (!q) return orders

    return orders.filter(o =>
      [
        o.customer_name,
        o.customer_phone,
        o.order_number,
        o.city,
        o.address,
        o.product_name,
        o.product_sku,
        o.offer_name,
        o.store_name,
        o.source
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(q)
    )
  }, [orders, search])

  const readyVisible = useMemo(
    () => filteredOrders.filter(isReady),
    [filteredOrders]
  )

  const selectedProduct = useMemo(
    () => products.find(p => p.id === manual.product_id),
    [products, manual.product_id]
  )

  const selectedOffer = useMemo(
    () => selectedProduct?.offers?.find(o => o.id === manual.offer_id),
    [selectedProduct, manual.offer_id]
  )

  const previewTotal = selectedOffer
    ? selectedOffer.price
    : selectedProduct
      ? Number(selectedProduct.selling_price || 0) *
        Number(manual.quantity || 1)
      : 0

  const loadManualMeta = async () => {
    setError('')

    try {
      const data = await api('/orders/manual-meta')
      const list = data.products || []

      setProducts(list)

      if (list.length) {
        setManual({
          ...emptyManual,
          product_id: list[0].id,
          quantity: list[0].default_qty || 1
        })
      }

      setManualOpen(true)
    } catch (e) {
      setError(e.message)
    }
  }

  const changeManualProduct = id => {
    const p = products.find(x => x.id === id)

    setManual({
      ...manual,
      product_id: id,
      offer_id: '',
      quantity: p?.default_qty || 1
    })
  }

  const changeOffer = id => {
    const offer = selectedProduct?.offers?.find(x => x.id === id)

    setManual({
      ...manual,
      offer_id: id,
      quantity:
        offer?.quantity ||
        selectedProduct?.default_qty ||
        1
    })
  }

  const createManualOrder = async e => {
    e.preventDefault()

    if (!selectedProduct) return

    setSavingManual(true)
    setError('')

    try {
      await api('/orders/manual', {
        method: 'POST',
        body: {
          store_id: selectedProduct.store_id,
          product_id: selectedProduct.id,
          offer_id: manual.offer_id || null,
          customer_name: manual.customer_name,
          phone: manual.phone,
          city: manual.city,
          address: manual.address,
          quantity: Number(manual.quantity || 1),
          unit_price: null,
          total_price: null,
          assigned_agent_id: null,
          source: 'MANUAL',
          call_status: 'NEW',
          call_note: manual.call_note
        }
      })

      setManualOpen(false)
      setManual(emptyManual)
      setNotice(t('Order created successfully.'))
      setBucket('NEW')
      await fetchData('NEW')
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingManual(false)
    }
  }

  const canEditOrder = order =>
    order &&
    !order.delivery_tracking &&
    !blockedDelivery.includes(order.delivery_status)

  const openEditOrder = order => {
    setSelected(order)

    setEditForm({
      customer_name: order.customer_name || '',
      phone: order.customer_phone || '',
      city: order.city || '',
      address: order.address || '',
      quantity: Number(order.quantity || 1),
      unit_price: order.unit_price ?? '',
      total_price: order.total_price ?? '',
      call_note: order.call_note || ''
    })

    setEditOpen(true)
  }

  const changeEditQuantity = value => {
    setEditForm(f => ({
      ...f,
      quantity: value,
      total_price:
        value !== '' && f.unit_price !== ''
          ? (Number(value) * Number(f.unit_price)).toFixed(2)
          : f.total_price
    }))
  }

  const changeEditUnitPrice = value => {
    setEditForm(f => ({
      ...f,
      unit_price: value,
      total_price:
        value !== '' && f.quantity !== ''
          ? (Number(value) * Number(f.quantity)).toFixed(2)
          : f.total_price
    }))
  }

  const saveEditOrder = async e => {
    e.preventDefault()

    if (!selected) return

    if (!editForm.city) {
      setError(t('Select a Digylog city.'))
      return
    }

    setSavingEdit(true)
    setError('')

    try {
      await api(`/orders/${selected.id}`, {
        method: 'PATCH',
        body: {
          customer_name: editForm.customer_name.trim(),
          phone: editForm.phone.trim(),
          city: editForm.city,
          address: editForm.address,
          quantity: Number(editForm.quantity),
          unit_price: Number(editForm.unit_price),
          total_price: Number(editForm.total_price),
          call_note: editForm.call_note
        }
      })

      setEditOpen(false)
      setNotice(t('Order updated successfully.'))
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingEdit(false)
    }
  }

  const outcome = async (order, status) => {
    if (!order) return

    setError('')

    try {
      await api(`/orders/${order.id}/call-attempts`, {
        method: 'POST',
        body: {
          outcome: status,
          channel: 'PHONE'
        }
      })

      setNotice(
        `${order.customer_name} → ${statusText(status)}`
      )

      await refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  const openCallback = order => {
    setSelected(order)
    setCbTime('')
    setCbNote(order.call_note || '')
    setCbOpen(true)
  }

  const callback = async e => {
    e.preventDefault()

    if (!selected) return

    setError('')

    try {
      await api(`/orders/${selected.id}/callbacks`, {
        method: 'POST',
        body: {
          scheduled_at: new Date(cbTime).toISOString(),
          reason: 'Customer callback',
          note: cbNote
        }
      })

      setCbOpen(false)
      setCbTime('')
      setCbNote('')
      setNotice(t('Callback scheduled.'))

      await refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  const dispatchDigylog = async order => {
    setDispatchingId(order.id)
    setError('')

    try {
      const r = await api(
        `/integrations/digylog/dispatch/${order.id}`,
        { method: 'POST' }
      )

      setNotice(
        `${t('Sent to Digylog. Tracking:')} ${
          r.tracking_number || 'created'
        }`
      )

      await refresh()
    } catch (e) {
      try {
        const blacklisted = await api(
          '/orders/my-queue?bucket=BLACKLIST&limit=200'
        )

        if (blacklisted.some(x => x.id === order.id)) {
          setError(
            t(
              'Digylog rejected this phone number because it is blacklisted. Edit the phone or customer information, then retry.'
            )
          )
          setBucket('BLACKLIST')
        } else {
          setError(e.message)
        }
      } catch {
        setError(e.message)
      }
    } finally {
      setDispatchingId(null)
    }
  }

  const toggleSelected = id => {
    setSelectedIds(current =>
      current.includes(id)
        ? current.filter(x => x !== id)
        : [...current, id]
    )
  }

  const selectAllReady = () => {
    const ids = readyVisible.map(o => o.id)

    const allAlready = ids.every(id =>
      selectedIds.includes(id)
    )

    if (allAlready) {
      setSelectedIds(current =>
        current.filter(id => !ids.includes(id))
      )
    } else {
      setSelectedIds(current =>
        Array.from(new Set([...current, ...ids]))
      )
    }
  }

  const bulkDispatch = async () => {
    if (!selectedIds.length) return

    setBulkBusy(true)
    setBulkResult(null)
    setError('')

    try {
      const result = await api(
        '/integrations/digylog/dispatch-bulk',
        {
          method: 'POST',
          body: {
            order_ids: selectedIds
          }
        }
      )

      const failures = (result.results || [])
        .filter(x => !x.ok)
        .slice(0, 5)

      setBulkResult({
        sent: result.sent || 0,
        failed: result.failed || 0,
        failures
      })

      setSelectedIds([])
      await refresh()
    } catch (e) {
      setError(e.message)
    } finally {
      setBulkBusy(false)
    }
  }

  const tabItems = [
    ['NEW', t('New'), counts.new],
    ['FOLLOW_UP', t('Follow-up'), counts.followUp],
    ['CONFIRMED', t('Confirmed'), counts.confirmed],
    ['READY', t('Ready to Send'), counts.ready],
    ['BLACKLIST', t('Blacklist'), counts.blacklist],
    ['ALL', t('All'), counts.all]
  ]

  const formatCreated = value => {
    if (!value) return '—'

    try {
      return date ? date(value) : new Date(value).toLocaleString()
    } catch {
      return '—'
    }
  }

  return (
    <>
      <div className="awv2">

        <section className="awv2-hero">
          <div>
            <span className="awv2-kicker">
              {t('COD OPS · AGENT DESK')}
            </span>

            <h1>{t('Call Workspace')}</h1>

            <p>
              {t(
                'Call customers, confirm orders and move ready orders to delivery.'
              )}
            </p>
          </div>

          <button
            className="btn awv2-manual"
            onClick={loadManualMeta}
          >
            + {t('Manual Order')}
          </button>
        </section>

        <section className="awv2-kpis">
          <div className="awv2-kpi">
            <span>{t('Assigned')}</span>
            <strong>{counts.all}</strong>
            <small>{t('My orders')}</small>
          </div>

          <div className="awv2-kpi">
            <span>{t('New')}</span>
            <strong>{counts.new}</strong>
            <small>{t('Waiting')}</small>
          </div>

          <div className="awv2-kpi">
            <span>{t('Follow-up')}</span>
            <strong>{counts.followUp}</strong>
            <small>{t('Need another call')}</small>
          </div>

          <div className="awv2-kpi success">
            <span>{t('Confirmed')}</span>
            <strong>{counts.confirmed}</strong>
            <small>{t('Accepted')}</small>
          </div>

          <div className="awv2-kpi ready">
            <span>{t('Ready to Send')}</span>
            <strong>{counts.ready}</strong>
            <small>Digylog</small>
          </div>

          <div className="awv2-kpi sent">
            <span>{t('Sent')}</span>
            <strong>{counts.sent}</strong>
            <small>{t('Delivery')}</small>
          </div>
        </section>

        {error && (
          <div className="error awv2-message">
            {error}
          </div>
        )}

        {notice && (
          <div className="awv2-notice">
            <strong>✓</strong>
            <span>{notice}</span>
            <button onClick={() => setNotice('')}>×</button>
          </div>
        )}

        {bulkResult && (
          <div
            className={
              bulkResult.failed
                ? 'awv2-bulk-result partial'
                : 'awv2-bulk-result'
            }
          >
            <div>
              <strong>
                {bulkResult.sent} {t('sent')}
              </strong>

              <span>
                {bulkResult.failed} {t('failed')}
              </span>
            </div>

            {bulkResult.failures.length > 0 && (
              <small>
                {bulkResult.failures
                  .map(x => x.error)
                  .join(' · ')}
              </small>
            )}

            <button onClick={() => setBulkResult(null)}>
              ×
            </button>
          </div>
        )}

        <section className="awv2-toolbar">
          <div className="awv2-search">
            <span>⌕</span>

            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={t(
                'Search customer, phone, city, order, product...'
              )}
            />

            {search && (
              <button onClick={() => setSearch('')}>
                ×
              </button>
            )}
          </div>

          <div className="awv2-tabs">
            {tabItems.map(([key, label, count]) => (
              <button
                key={key}
                className={
                  bucket === key
                    ? 'awv2-tab active'
                    : 'awv2-tab'
                }
                onClick={() => {
                  setBucket(key)
                  setSearch('')
                  setSelectedIds([])
                }}
              >
                <span>{label}</span>
                <b>{count}</b>
              </button>
            ))}
          </div>

          {readyVisible.length > 0 && (
            <button
              className="btn secondary awv2-select-all"
              onClick={selectAllReady}
            >
              {readyVisible.every(o =>
                selectedIds.includes(o.id)
              )
                ? t('Clear selection')
                : `${t('Select ready')} (${readyVisible.length})`}
            </button>
          )}
        </section>

        <div className="awv2-list-head">
          <div>
            <h2>{t('Orders')}</h2>
            <p>
              {filteredOrders.length} {t('orders in this view')}
            </p>
          </div>

          <button
            className="btn small secondary"
            onClick={refresh}
          >
            ↻ {t('Refresh')}
          </button>
        </div>

        {filteredOrders.length === 0 ? (
          <div className="awv2-empty">
            <div>✓</div>
            <h3>{t('Queue is clear')}</h3>
            <p>{t('No orders in this view.')}</p>
          </div>
        ) : (
          <section className="awv2-order-grid">
            {filteredOrders.map(order => {
              const sendable = isReady(order)
              const checked = selectedIds.includes(order.id)
              const blacklisted =
                order.call_status === 'BLACKLIST'

              return (
                <article
                  className={
                    checked
                      ? 'awv2-card selected'
                      : blacklisted
                        ? 'awv2-card blacklist'
                        : 'awv2-card'
                  }
                  key={order.id}
                >
                  <div className="awv2-card-top">
                    <div className="awv2-card-order">
                      {sendable && (
                        <label
                          className="awv2-check"
                          title={t('Select for Digylog')}
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() =>
                              toggleSelected(order.id)
                            }
                          />
                          <span />
                        </label>
                      )}

                      <div>
                        <small>{t('Order')}</small>
                        <strong>
                          {order.order_number || '—'}
                        </strong>
                      </div>
                    </div>

                    <div className="awv2-card-status">
                      <StatusBadge
                        value={order.call_status}
                      />

                      {order.delivery_status &&
                        order.delivery_status !== 'NOT_READY' && (
                          <StatusBadge
                            value={order.delivery_status}
                          />
                        )}
                    </div>
                  </div>

                  {blacklisted && (
                    <div className="awv2-blacklist-alert">
                      <strong>
                        {t('Digylog Blacklist')}
                      </strong>
                      <span>
                        {t(
                          'Correct the customer information before retrying delivery.'
                        )}
                      </span>
                    </div>
                  )}

                  <div className="awv2-customer">
                    <div>
                      <span className="awv2-label">
                        {t('Customer')}
                      </span>

                      <h3>
                        {order.customer_name || '—'}
                      </h3>

                      <a
                        className="awv2-phone"
                        href={`tel:${order.customer_phone}`}
                        dir="ltr"
                      >
                        {order.customer_phone || '—'}
                      </a>
                    </div>

                    <div className="awv2-price">
                      <span>{t('Total')}</span>
                      <strong>
                        {money(
                          order.total_price,
                          order.currency
                        )}
                      </strong>
                    </div>
                  </div>

                  <div className="awv2-info-grid">
                    <div>
                      <span>{t('City')}</span>
                      <strong>
                        {order.city || '—'}
                      </strong>
                    </div>

                    <div>
                      <span>{t('Store')}</span>
                      <strong>
                        {order.store_name || '—'}
                      </strong>
                    </div>

                    <div className="wide">
                      <span>{t('Address')}</span>
                      <strong>
                        {order.address ||
                          t('No address yet')}
                      </strong>
                    </div>
                  </div>

                  <div className="awv2-product">
                    <div className="awv2-product-icon">
                      P
                    </div>

                    <div className="awv2-product-copy">
                      <span>{t('Product')}</span>

                      <strong>
                        {order.product_name || '—'}
                      </strong>

                      <small>
                        {order.product_sku || '—'}
                      </small>
                    </div>

                    <div className="awv2-product-meta">
                      <div>
                        <span>{t('Offer')}</span>
                        <strong>
                          {order.offer_name ||
                            t('Standard')}
                        </strong>
                      </div>

                      <div>
                        <span>{t('Qty')}</span>
                        <strong>
                          {order.quantity || 1}
                        </strong>
                      </div>
                    </div>
                  </div>

                  {order.call_note && (
                    <div className="awv2-note">
                      <span>{t('Agent Note')}</span>
                      <p>{order.call_note}</p>
                    </div>
                  )}

                  <div className="awv2-meta-line">
                    <span>
                      {order.source === 'MANUAL' ? t('Manual') : (order.source || '—')}
                    </span>

                    <span>
                      {formatCreated(order.created_at)}
                    </span>

                    {order.delivery_tracking && (
                      <span className="track">
                        {t('Tracking')}: {order.delivery_tracking}
                      </span>
                    )}
                  </div>

                  <div className="awv2-primary-actions">
                    <button
                      className="awv2-action confirm"
                      onClick={() =>
                        outcome(order, 'CONFIRMED')
                      }
                    >
                      <strong>✓</strong>
                      <span>{t('Confirmed')}</span>
                    </button>

                    <button
                      className="awv2-action callback"
                      onClick={() =>
                        openCallback(order)
                      }
                    >
                      <strong>↻</strong>
                      <span>{t('Callback')}</span>
                    </button>

                    <a
                      className="awv2-action call"
                      href={`tel:${order.customer_phone}`}
                    >
                      <strong>☎</strong>
                      <span>{t('Call')}</span>
                    </a>

                    <a
                      className="awv2-action whatsapp"
                      href={`https://wa.me/${(
                        order.customer_phone || ''
                      ).replace(/\D/g, '')}`}
                      target="_blank"
                      rel="noreferrer"
                    >
                      <strong>W</strong>
                      <span>WhatsApp</span>
                    </a>
                  </div>

                  <div className="awv2-secondary-actions">
                    <button
                      onClick={() =>
                        outcome(order, 'NO_ANSWER')
                      }
                    >
                      {t('No Answer')}
                    </button>

                    <button
                      onClick={() =>
                        outcome(order, 'BUSY')
                      }
                    >
                      {t('Busy')}
                    </button>

                    <button
                      onClick={() =>
                        outcome(
                          order,
                          'NOT_INTERESTED'
                        )
                      }
                    >
                      {t('Not Interested')}
                    </button>

                    <button
                      onClick={() =>
                        outcome(
                          order,
                          'WRONG_NUMBER'
                        )
                      }
                    >
                      {t('Wrong Number')}
                    </button>

                    {canEditOrder(order) && (
                      <button
                        className="edit"
                        onClick={() =>
                          openEditOrder(order)
                        }
                      >
                        {t('Edit')}
                      </button>
                    )}
                  </div>

                  {(sendable || blacklisted) &&
                    !isSent(order) && (
                      <button
                        className={
                          blacklisted
                            ? 'awv2-send retry'
                            : 'awv2-send'
                        }
                        disabled={
                          dispatchingId === order.id
                        }
                        onClick={() =>
                          dispatchDigylog(order)
                        }
                      >
                        {dispatchingId === order.id
                          ? t('Sending...')
                          : blacklisted
                            ? t('Retry Send to Digylog')
                            : t('Send to Digylog')}
                      </button>
                    )}
                </article>
              )
            })}
          </section>
        )}

        {selectedIds.length > 0 && (
          <div className="awv2-bulk-bar">
            <div>
              <span>
                {t('Selected')}
              </span>

              <strong>
                {selectedIds.length}
              </strong>

              <small>
                {t('confirmed orders ready for Digylog')}
              </small>
            </div>

            <div className="awv2-bulk-buttons">
              <button
                className="btn secondary"
                onClick={() => setSelectedIds([])}
                disabled={bulkBusy}
              >
                {t('Clear')}
              </button>

              <button
                className="btn awv2-bulk-send"
                onClick={bulkDispatch}
                disabled={bulkBusy}
              >
                {bulkBusy
                  ? t('Sending...')
                  : `${t('Send Selected to Digylog')} (${selectedIds.length})`}
              </button>
            </div>
          </div>
        )}
      </div>

      <Modal
        open={manualOpen}
        title="Add Manual Order"
        onClose={() => setManualOpen(false)}
        wide
      >
        {products.length === 0 ? (
          <div className="empty">
            {t(
              'No products are assigned to your agent account.'
            )}
          </div>
        ) : (
          <form onSubmit={createManualOrder}>
            <div className="form-grid">

              <div className="field full">
                <label>{t('Product')}</label>

                <select
                  required
                  value={manual.product_id}
                  onChange={e =>
                    changeManualProduct(e.target.value)
                  }
                >
                  {products.map(p => (
                    <option
                      key={p.id}
                      value={p.id}
                    >
                      {p.name} — {p.sku}
                    </option>
                  ))}
                </select>
              </div>

              {selectedProduct?.offers?.length > 0 && (
                <div className="field full">
                  <label>{t('Offer')}</label>

                  <select
                    value={manual.offer_id}
                    onChange={e =>
                      changeOffer(e.target.value)
                    }
                  >
                    <option value="">
                      {t('Standard price')}
                    </option>

                    {selectedProduct.offers.map(o => (
                      <option
                        key={o.id}
                        value={o.id}
                      >
                        {o.name} — {o.quantity} pcs —{' '}
                        {money(
                          o.price,
                          selectedProduct.currency
                        )}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="field">
                <label>{t('Customer Name')}</label>

                <input
                  required
                  value={manual.customer_name}
                  onChange={e =>
                    setManual({
                      ...manual,
                      customer_name: e.target.value
                    })
                  }
                />
              </div>

              <div className="field">
                <label>{t('Phone')}</label>

                <input
                  required
                  value={manual.phone}
                  onChange={e =>
                    setManual({
                      ...manual,
                      phone: e.target.value
                    })
                  }
                />
              </div>

              <CitySelect
                value={manual.city}
                onChange={city =>
                  setManual({
                    ...manual,
                    city
                  })
                }
                label={t('City')}
                placeholder={t('Type city name...')}
              />

              <div className="field">
                <label>{t('Quantity')}</label>

                <input
                  type="number"
                  min="1"
                  required
                  disabled={!!manual.offer_id}
                  value={manual.quantity}
                  onChange={e =>
                    setManual({
                      ...manual,
                      quantity: e.target.value
                    })
                  }
                />
              </div>

              <div className="field full">
                <label>{t('Address')}</label>

                <textarea
                  value={manual.address}
                  onChange={e =>
                    setManual({
                      ...manual,
                      address: e.target.value
                    })
                  }
                />
              </div>

              <div className="field full">
                <label>{t('Note')}</label>

                <textarea
                  value={manual.call_note}
                  onChange={e =>
                    setManual({
                      ...manual,
                      call_note: e.target.value
                    })
                  }
                />
              </div>

              <div className="field full">
                <div className="panel">
                  <strong>{t('Order Total')}</strong>

                  <div
                    style={{
                      fontSize: 24,
                      fontWeight: 800,
                      marginTop: 6
                    }}
                  >
                    {money(
                      previewTotal,
                      selectedProduct?.currency ||
                        'MAD'
                    )}
                  </div>

                  <small>
                    {t(
                      'This order will automatically be assigned to you and created as NEW.'
                    )}
                  </small>
                </div>
              </div>
            </div>

            <div className="form-actions">
              <button
                type="button"
                className="btn secondary"
                onClick={() =>
                  setManualOpen(false)
                }
              >
                {t('Cancel')}
              </button>

              <button
                className="btn"
                disabled={savingManual}
              >
                {savingManual
                  ? t('Creating...')
                  : t('Create Order')}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <Modal
        open={editOpen}
        title={t('Edit Order')}
        onClose={() => setEditOpen(false)}
        wide
      >
        <form onSubmit={saveEditOrder}>
          <div className="form-grid">

            <div className="field">
              <label>{t('Customer Name')}</label>
              <input
                required
                value={editForm.customer_name}
                onChange={e =>
                  setEditForm({
                    ...editForm,
                    customer_name: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Phone')}</label>
              <input
                required
                value={editForm.phone}
                onChange={e =>
                  setEditForm({
                    ...editForm,
                    phone: e.target.value
                  })
                }
              />
            </div>

            <CitySelect
              value={editForm.city}
              onChange={city =>
                setEditForm({
                  ...editForm,
                  city
                })
              }
              label={t('City')}
              placeholder={t('Type city name...')}
            />

            <div className="field">
              <label>{t('Quantity')}</label>
              <input
                type="number"
                min="1"
                required
                value={editForm.quantity}
                onChange={e =>
                  changeEditQuantity(
                    e.target.value
                  )
                }
              />
            </div>

            <div className="field">
              <label>{t('Unit Price')}</label>
              <input
                type="number"
                min="0"
                step="0.01"
                required
                value={editForm.unit_price}
                onChange={e =>
                  changeEditUnitPrice(
                    e.target.value
                  )
                }
              />
            </div>

            <div className="field">
              <label>{t('Total Price')}</label>
              <input
                type="number"
                min="0"
                step="0.01"
                required
                value={editForm.total_price}
                onChange={e =>
                  setEditForm({
                    ...editForm,
                    total_price:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field full">
              <label>{t('Address')}</label>
              <textarea
                value={editForm.address}
                onChange={e =>
                  setEditForm({
                    ...editForm,
                    address: e.target.value
                  })
                }
              />
            </div>

            <div className="field full">
              <label>{t('Note')}</label>
              <textarea
                value={editForm.call_note}
                onChange={e =>
                  setEditForm({
                    ...editForm,
                    call_note: e.target.value
                  })
                }
              />
            </div>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() => setEditOpen(false)}
            >
              {t('Cancel')}
            </button>

            <button
              className="btn success"
              disabled={savingEdit}
            >
              {savingEdit
                ? t('Saving...')
                : t('Save Changes')}
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        open={cbOpen}
        title="Schedule Callback"
        onClose={() => setCbOpen(false)}
      >
        <form onSubmit={callback}>

          <div className="field">
            <label>{t('Date & Time')}</label>

            <input
              type="datetime-local"
              required
              value={cbTime}
              onChange={e =>
                setCbTime(e.target.value)
              }
            />
          </div>

          <div className="field">
            <label>{t('Note')}</label>

            <textarea
              value={cbNote}
              onChange={e =>
                setCbNote(e.target.value)
              }
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() => setCbOpen(false)}
            >
              {t('Cancel')}
            </button>

            <button className="btn">
              {t('Schedule')}
            </button>
          </div>
        </form>
      </Modal>
    </>
  )
}
