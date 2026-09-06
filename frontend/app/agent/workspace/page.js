'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, money } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import Modal from '../../../components/Modal'
import StatusBadge from '../../../components/StatusBadge'

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

export default function WorkspacePage() {
  const { t, status: statusText } = useI18n()

  const [bucket, setBucket] = useState('NEW')
  const [orders, setOrders] = useState([])
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState('')

  const [cbOpen, setCbOpen] = useState(false)
  const [cbTime, setCbTime] = useState('')
  const [cbNote, setCbNote] = useState('')

  const [manualOpen, setManualOpen] = useState(false)
  const [products, setProducts] = useState([])
  const [manual, setManual] = useState(emptyManual)
  const [savingManual, setSavingManual] = useState(false)

  const load = () =>
    api(`/orders/my-queue?bucket=${bucket}`)
      .then(rows => {
        setOrders(rows)
        setSelected(s => rows.find(x => x.id === s?.id) || rows[0] || null)
      })
      .catch(e => setError(e.message))

  useEffect(() => {
    load()
  }, [bucket])

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

  const selectedProduct = useMemo(
    () => products.find(p => p.id === manual.product_id),
    [products, manual.product_id]
  )

  const selectedOffer = useMemo(
    () => selectedProduct?.offers?.find(o => o.id === manual.offer_id),
    [selectedProduct, manual.offer_id]
  )

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
      quantity: offer?.quantity || selectedProduct?.default_qty || 1
    })
  }

  const previewTotal = selectedOffer
    ? selectedOffer.price
    : selectedProduct
      ? Number(selectedProduct.selling_price || 0) * Number(manual.quantity || 1)
      : 0

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

      if (bucket !== 'NEW') {
        setBucket('NEW')
      } else {
        await load()
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingManual(false)
    }
  }

  const outcome = async status => {
    if (!selected) return

    try {
      await api(`/orders/${selected.id}/call-attempts`, {
        method: 'POST',
        body: {
          outcome: status,
          channel: 'PHONE'
        }
      })

      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const callback = async e => {
    e.preventDefault()

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
      await load()
    } catch (err) {
      setError(err.message)
    }
  }

  const dispatchDigylog = async () => {
    if (!selected) return

    setError('')

    try {
      const r = await api(`/integrations/digylog/dispatch/${selected.id}`, {
        method: 'POST'
      })

      alert(`${t('Sent to Digylog. Tracking:')} ${r.tracking_number || 'created'}`)
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('Call Workspace')}</h1>
          <p>{t('Call → outcome → save → next order.')}</p>
        </div>

        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
          <button className="btn" onClick={loadManualMeta}>
            {t('+ Manual Order')}
          </button>

          <div className="tabs">
            {['NEW', 'FOLLOW_UP', 'CONFIRMED', 'ALL'].map(x => (
              <button
                key={x}
                className={bucket === x ? 'tab active' : 'tab'}
                onClick={() => setBucket(x)}
              >
                {statusText(x)}
              </button>
            ))}
          </div>
        </div>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="workspace-grid">
        <div className="order-focus">
          {selected ? (
            <>
              <StatusBadge value={selected.call_status} />

              <h2>{selected.customer_name}</h2>

              <div className="customer-phone">
                {selected.customer_phone}
              </div>

              <p>
                {selected.city || t('No city')} ·{' '}
                {selected.address || t('No address yet')}
              </p>

              <div className="panel" style={{ marginTop: 16 }}>
                <strong>{selected.product_name}</strong>
                <div>
                  {selected.product_sku} · {t('Quantity')} {selected.quantity} ·{' '}
                  {money(selected.total_price, selected.currency)}
                </div>
              </div>

              <div className="action-grid">
                <button
                  className="btn success"
                  onClick={() => outcome('CONFIRMED')}
                >
                  {t('Confirmed')}
                </button>

                <button
                  className="btn secondary"
                  onClick={() => outcome('NO_ANSWER')}
                >
                  {t('No Answer')}
                </button>

                <button
                  className="btn secondary"
                  onClick={() => outcome('BUSY')}
                >
                  {t('Busy')}
                </button>

                <button
                  className="btn warning"
                  onClick={() => setCbOpen(true)}
                >
                  {t('Callback')}
                </button>

                <button
                  className="btn danger"
                  onClick={() => outcome('CANCELLED')}
                >
                  {t('Cancelled')}
                </button>

                <button
                  className="btn secondary"
                  onClick={() => outcome('WRONG_NUMBER')}
                >
                  {t('Wrong Number')}
                </button>
              </div>

              <div
                className="form-actions"
                style={{
                  justifyContent: 'flex-start',
                  flexWrap: 'wrap'
                }}
              >
                <a
                  className="btn secondary"
                  href={`tel:${selected.customer_phone}`}
                >
                  {t('Call phone')}
                </a>

                <a
                  className="btn secondary"
                  href={`https://wa.me/${(selected.customer_phone || '').replace(/\D/g, '')}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  WhatsApp
                </a>

                {selected.call_status === 'CONFIRMED' &&
                  ![
                    'DISPATCHED',
                    'IN_TRANSIT',
                    'OUT_FOR_DELIVERY',
                    'DELIVERED'
                  ].includes(selected.delivery_status) && (
                    <button
                      className="btn warning"
                      onClick={dispatchDigylog}
                    >
                      {t('Send Digylog')}
                    </button>
                  )}

                {selected.delivery_tracking && (
                  <span className="badge ok">
                    {t('Tracking')}: {selected.delivery_tracking}
                  </span>
                )}
              </div>
            </>
          ) : (
            <div className="empty">
              {t('No orders in this queue.')}
            </div>
          )}
        </div>

        <div>
          <div className="panel-head" style={{ marginBottom: 10 }}>
            <h3>
              {t('Queue')} ({orders.length})
            </h3>
          </div>

          <div className="queue-list">
            {orders.map(o => (
              <div
                key={o.id}
                className={
                  selected?.id === o.id
                    ? 'queue-item active'
                    : 'queue-item'
                }
                onClick={() => setSelected(o)}
              >
                <strong>{o.customer_name}</strong>
                <br />
                <small>
                  {o.product_name} · {o.city || t('No city')} ·{' '}
                  {statusText(o.call_status)}
                </small>
              </div>
            ))}
          </div>
        </div>
      </div>

      <Modal
        open={manualOpen}
        title="Add Manual Order"
        onClose={() => setManualOpen(false)}
        wide
      >
        {products.length === 0 ? (
          <div className="empty">
            {t('No products are assigned to your agent account.')}
          </div>
        ) : (
          <form onSubmit={createManualOrder}>
            <div className="form-grid">

              <div className="field full">
                <label>{t('Product')}</label>
                <select
                  required
                  value={manual.product_id}
                  onChange={e => changeManualProduct(e.target.value)}
                >
                  {products.map(p => (
                    <option key={p.id} value={p.id}>
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
                    onChange={e => changeOffer(e.target.value)}
                  >
                    <option value="">
                      {t('Standard price')}
                    </option>

                    {selectedProduct.offers.map(o => (
                      <option key={o.id} value={o.id}>
                        {o.name} — {o.quantity} pcs —{' '}
                        {money(o.price, selectedProduct.currency)}
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

              <div className="field">
                <label>{t('City')}</label>
                <input
                  value={manual.city}
                  onChange={e =>
                    setManual({
                      ...manual,
                      city: e.target.value
                    })
                  }
                />
              </div>

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
                  <div style={{ fontSize: 22, marginTop: 6 }}>
                    {money(
                      previewTotal,
                      selectedProduct?.currency || 'MAD'
                    )}
                  </div>
                  <small>
                    {t('This order will automatically be assigned to you and created as NEW.')}
                  </small>
                </div>
              </div>

            </div>

            <div className="form-actions">
              <button
                type="button"
                className="btn secondary"
                onClick={() => setManualOpen(false)}
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
              onChange={e => setCbTime(e.target.value)}
            />
          </div>

          <div className="field">
            <label>{t('Note')}</label>
            <textarea
              value={cbNote}
              onChange={e => setCbNote(e.target.value)}
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
