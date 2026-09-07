'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, money } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import Modal from '../../../components/Modal'
import CitySelect from '../../../components/CitySelect'

const EMPTY_BOARD = {
  counts: {
    new: 0,
    follow_up: 0,
    ready: 0,
    blacklist: 0,
    closed: 0,
    sent: 0,
    all: 0
  },
  products: [],
  orders: []
}

const EMPTY_MANUAL = {
  product_id: '',
  offer_id: '',
  customer_name: '',
  phone: '',
  city: '',
  address: '',
  call_note: ''
}

const LOCKED_DELIVERY = new Set([
  'DISPATCHED',
  'IN_TRANSIT',
  'OUT_FOR_DELIVERY',
  'DELIVERED'
])


const draftFromOrder = order => ({
  customer_name: order.customer_name || '',
  phone: order.customer_phone || '',
  city: order.city || '',
  address: order.address || '',
  offer_id: order.offer_id || '',
  call_note: order.call_note || ''
})

const phoneForWhatsApp = value => String(value || '').replace(/\D/g, '')

export default function WorkspacePage() {
  const { locale, date } = useI18n()
  const isAr = locale === 'ar'
  const L = (en, ar) => (isAr ? ar : en)

  const [bucket, setBucket] = useState('NEW')
  const [productId, setProductId] = useState('')
  const [board, setBoard] = useState(EMPTY_BOARD)
  const [drafts, setDrafts] = useState({})
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [savingId, setSavingId] = useState(null)
  const [dispatchingId, setDispatchingId] = useState(null)

  const [selectedIds, setSelectedIds] = useState([])
  const [bulkBusy, setBulkBusy] = useState(false)
  const [bulkResult, setBulkResult] = useState(null)

  const [manualOpen, setManualOpen] = useState(false)
  const [manualProducts, setManualProducts] = useState([])
  const [manual, setManual] = useState(EMPTY_MANUAL)
  const [savingManual, setSavingManual] = useState(false)

  const [callbackOpen, setCallbackOpen] = useState(false)
  const [callbackOrder, setCallbackOrder] = useState(null)
  const [callbackAt, setCallbackAt] = useState('')
  const [callbackNote, setCallbackNote] = useState('')
  const [callbackBusy, setCallbackBusy] = useState(false)

  const statusLabel = value => {
    const map = {
      NEW: L('New', 'جديد'),
      NO_ANSWER: L('No answer', 'لا يجيب'),
      VOICEMAIL: L('Voicemail', 'صندوق صوتي'),
      BUSY: L('Busy', 'مشغول'),
      CALLBACK: L('Follow-up', 'متابعة'),
      CONFIRMED: L('Confirmed', 'مؤكد'),
      BLACKLIST: L('Blacklist', 'القائمة السوداء'),
      CANCELLED: L('Cancelled', 'ملغى'),
      WRONG_NUMBER: L('Wrong number', 'رقم خاطئ'),
      DUPLICATE: L('Duplicate', 'طلب مكرر'),
      NOT_INTERESTED: L('Not interested', 'غير مهتم'),
      NOT_READY: L('Not ready', 'غير جاهز'),
      READY: L('Ready to send', 'جاهز للإرسال'),
      DISPATCHED: L('Sent', 'تم الإرسال'),
      IN_TRANSIT: L('In transit', 'في الطريق'),
      OUT_FOR_DELIVERY: L('Out for delivery', 'خارج للتسليم'),
      DELIVERED: L('Delivered', 'تم التسليم'),
      REFUSED: L('Refused', 'مرفوض'),
      RETURNED: L('Returned', 'مرتجع'),
      ISSUE: L('Delivery issue', 'مشكلة توصيل')
    }
    return map[value] || String(value || '—').replaceAll('_', ' ')
  }

  const loadBoard = async (nextBucket = bucket, nextProductId = productId) => {
    setLoading(true)
    setError('')

    try {
      const params = new URLSearchParams({
        bucket: nextBucket,
        limit: '200'
      })

      if (nextProductId) params.set('product_id', nextProductId)

      const data = await api(`/orders/agent-board?${params.toString()}`)
      const safe = {
        counts: data.counts || EMPTY_BOARD.counts,
        products: data.products || [],
        orders: data.orders || []
      }

      setBoard(safe)

      const nextDrafts = {}
      for (const order of safe.orders) nextDrafts[order.id] = draftFromOrder(order)
      setDrafts(nextDrafts)

      setSelectedIds(current =>
        current.filter(id =>
          safe.orders.some(
            order =>
              order.id === id &&
              order.call_status === 'CONFIRMED' &&
              order.delivery_status === 'READY'
          )
        )
      )
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadBoard(bucket, productId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bucket, productId])

  const setDraftField = (orderId, key, value) => {
    setDrafts(current => ({
      ...current,
      [orderId]: {
        ...(current[orderId] || {}),
        [key]: value
      }
    }))
  }

  const filteredOrders = useMemo(() => {
    const q = search.trim().toLowerCase()
    if (!q) return board.orders

    return board.orders.filter(order =>
      [
        order.order_number,
        order.customer_name,
        order.customer_phone,
        order.product_name,
        order.product_sku,
        order.offer_name,
        order.city,
        order.address,
        order.store_name,
        order.source,
        order.delivery_tracking
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase()
        .includes(q)
    )
  }, [board.orders, search])

  const currentBucketCount = useMemo(() => {
    const c = board.counts || EMPTY_BOARD.counts
    const map = {
      NEW: c.new,
      FOLLOW_UP: c.follow_up,
      READY: c.ready,
      BLACKLIST: c.blacklist,
      CLOSED: c.closed,
      SENT: c.sent,
      ALL: c.all
    }
    return map[bucket] ?? 0
  }, [board.counts, bucket])

  const tabs = [
    ['NEW', L('New orders', 'طلبات جديدة'), board.counts.new],
    ['FOLLOW_UP', L('Follow-up', 'للمتابعة'), board.counts.follow_up],
    ['READY', L('Ready to send', 'للإرسال'), board.counts.ready],
    ['BLACKLIST', L('Blacklist', 'القائمة السوداء'), board.counts.blacklist],
    ['CLOSED', L('Draft / Closed', 'مسودة / مغلقة'), board.counts.closed],
    ['SENT', L('Sent', 'تم الإرسال'), board.counts.sent],
    ['ALL', L('All', 'الكل'), board.counts.all]
  ]

  const kpis = [
    [L('New', 'جديدة'), board.counts.new, 'new'],
    [L('Follow-up', 'متابعة'), board.counts.follow_up, 'follow'],
    [L('Ready', 'للإرسال'), board.counts.ready, 'ready'],
    [L('Blacklist', 'سوداء'), board.counts.blacklist, 'blacklist'],
    [L('Closed', 'مغلقة'), board.counts.closed, 'closed'],
    [L('Sent', 'مرسلة'), board.counts.sent, 'sent']
  ]

  const buildWorkflowBody = (order, outcome = null) => {
    const draft = drafts[order.id] || draftFromOrder(order)
    const body = {
      customer_name: String(draft.customer_name || '').trim(),
      phone: String(draft.phone || '').trim(),
      city: draft.city || '',
      address: String(draft.address || '').trim(),
      call_note: String(draft.call_note || '').trim()
    }

    if ((draft.offer_id || '') !== (order.offer_id || '')) {
      body.offer_id = draft.offer_id || ''
    }

    if (outcome) body.outcome = outcome
    return body
  }

  const validateConfirmation = order => {
    const draft = drafts[order.id] || draftFromOrder(order)

    if (!String(draft.customer_name || '').trim()) {
      return L('Customer name is required.', 'اسم العميل مطلوب.')
    }
    if (!String(draft.phone || '').trim()) {
      return L('Phone number is required.', 'رقم الهاتف مطلوب.')
    }
    if (!draft.offer_id) {
      return L('Select an active product offer.', 'اختر عرضاً نشطاً للمنتج.')
    }
    if (!draft.city) {
      return L('Select a Digylog city.', 'اختر مدينة صحيحة من Digylog.')
    }
    if (!String(draft.address || '').trim()) {
      return L('Customer address is required.', 'عنوان العميل مطلوب.')
    }
    return ''
  }

  const saveOrder = async (order, outcome = null) => {
    if (!order?.editable) return

    if (outcome === 'CONFIRMED') {
      const validation = validateConfirmation(order)
      if (validation) {
        setError(validation)
        return
      }
    }

    setSavingId(order.id)
    setError('')
    setNotice('')

    try {
      await api(`/orders/agent-workflow/${order.id}`, {
        method: 'POST',
        body: buildWorkflowBody(order, outcome)
      })

      setNotice(
        outcome
          ? `${order.customer_name || order.order_number} → ${statusLabel(outcome)}`
          : L('Changes saved successfully.', 'تم حفظ التعديلات بنجاح.')
      )

      await loadBoard(bucket, productId)
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingId(null)
    }
  }

  const openCallback = order => {
    setCallbackOrder(order)
    setCallbackAt('')
    setCallbackNote((drafts[order.id]?.call_note || order.call_note || '').trim())
    setCallbackOpen(true)
  }

  const saveCallback = async e => {
    e.preventDefault()
    if (!callbackOrder || !callbackAt) return

    setCallbackBusy(true)
    setError('')

    try {
      const draft = drafts[callbackOrder.id] || draftFromOrder(callbackOrder)
      setDrafts(current => ({
        ...current,
        [callbackOrder.id]: {
          ...draft,
          call_note: callbackNote
        }
      }))

      const body = buildWorkflowBody(callbackOrder, 'CALLBACK')
      body.call_note = callbackNote

      await api(`/orders/agent-workflow/${callbackOrder.id}`, {
        method: 'POST',
        body
      })

      await api(`/orders/${callbackOrder.id}/callbacks`, {
        method: 'POST',
        body: {
          scheduled_at: new Date(callbackAt).toISOString(),
          reason: 'Customer callback',
          note: callbackNote
        }
      })

      setCallbackOpen(false)
      setCallbackOrder(null)
      setCallbackAt('')
      setCallbackNote('')
      setNotice(L('Follow-up scheduled.', 'تمت جدولة المتابعة.'))
      await loadBoard(bucket, productId)
    } catch (e) {
      setError(e.message)
    } finally {
      setCallbackBusy(false)
    }
  }

  const dispatchDigylog = async order => {
    setDispatchingId(order.id)
    setError('')
    setNotice('')

    try {
      const result = await api(`/integrations/digylog/dispatch/${order.id}`, {
        method: 'POST'
      })

      setNotice(
        `${L('Sent to Digylog', 'تم الإرسال إلى Digylog')}${
          result.tracking_number ? ` · ${result.tracking_number}` : ''
        }`
      )
      await loadBoard(bucket, productId)
    } catch (e) {
      try {
        const black = await api('/orders/agent-board?bucket=BLACKLIST&limit=200')
        const moved = (black.orders || []).some(item => item.id === order.id)
        if (moved) {
          setBucket('BLACKLIST')
          setProductId('')
          setError(
            L(
              'Digylog rejected this order as blacklisted. Correct the customer information and retry.',
              'رفض Digylog هذا الطلب بسبب القائمة السوداء. صحح بيانات العميل ثم أعد الإرسال.'
            )
          )
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

  const readyVisible = useMemo(
    () =>
      filteredOrders.filter(
        order => order.call_status === 'CONFIRMED' && order.delivery_status === 'READY'
      ),
    [filteredOrders]
  )

  const toggleSelected = id => {
    setSelectedIds(current =>
      current.includes(id) ? current.filter(x => x !== id) : [...current, id]
    )
  }

  const selectAllReady = () => {
    const ids = readyVisible.map(order => order.id)
    const allSelected = ids.length > 0 && ids.every(id => selectedIds.includes(id))

    setSelectedIds(current =>
      allSelected
        ? current.filter(id => !ids.includes(id))
        : Array.from(new Set([...current, ...ids]))
    )
  }

  const bulkDispatch = async () => {
    if (!selectedIds.length) return

    setBulkBusy(true)
    setError('')
    setBulkResult(null)

    try {
      const result = await api('/integrations/digylog/dispatch-bulk', {
        method: 'POST',
        body: { order_ids: selectedIds }
      })

      setBulkResult({
        sent: result.sent || 0,
        failed: result.failed || 0,
        failures: (result.results || []).filter(x => !x.ok).slice(0, 5)
      })

      setSelectedIds([])
      await loadBoard(bucket, productId)
    } catch (e) {
      setError(e.message)
    } finally {
      setBulkBusy(false)
    }
  }

  const loadManualMeta = async () => {
    setError('')

    try {
      const data = await api('/orders/manual-meta')
      const list = data.products || []
      setManualProducts(list)

      if (list.length) {
        const first = list[0]
        const firstOffer = first.offers?.[0]
        setManual({
          ...EMPTY_MANUAL,
          product_id: first.id,
          offer_id: firstOffer?.id || ''
        })
      } else {
        setManual(EMPTY_MANUAL)
      }

      setManualOpen(true)
    } catch (e) {
      setError(e.message)
    }
  }

  const manualProduct = useMemo(
    () => manualProducts.find(product => product.id === manual.product_id),
    [manualProducts, manual.product_id]
  )

  const manualOffer = useMemo(
    () => manualProduct?.offers?.find(offer => offer.id === manual.offer_id),
    [manualProduct, manual.offer_id]
  )

  const changeManualProduct = id => {
    const product = manualProducts.find(item => item.id === id)
    setManual(current => ({
      ...current,
      product_id: id,
      offer_id: product?.offers?.[0]?.id || ''
    }))
  }

  const createManualOrder = async e => {
    e.preventDefault()

    if (!manualProduct) return
    if (!manualOffer) {
      setError(L('This product needs an active offer.', 'هذا المنتج يحتاج إلى عرض نشط.'))
      return
    }
    if (!manual.city) {
      setError(L('Select a Digylog city.', 'اختر مدينة صحيحة من Digylog.'))
      return
    }

    setSavingManual(true)
    setError('')

    try {
      await api('/orders/manual', {
        method: 'POST',
        body: {
          store_id: manualProduct.store_id,
          product_id: manualProduct.id,
          offer_id: manualOffer.id,
          customer_name: manual.customer_name.trim(),
          phone: manual.phone.trim(),
          city: manual.city,
          address: manual.address.trim(),
          quantity: Number(manualOffer.quantity || 1),
          unit_price: null,
          total_price: null,
          assigned_agent_id: null,
          source: 'MANUAL',
          call_status: 'NEW',
          call_note: manual.call_note.trim()
        }
      })

      setManualOpen(false)
      setManual(EMPTY_MANUAL)
      setBucket('NEW')
      setProductId('')
      setNotice(L('Order created successfully.', 'تم إنشاء الطلب بنجاح.'))
      await loadBoard('NEW', '')
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingManual(false)
    }
  }

  const formatDate = value => {
    if (!value) return '—'
    try {
      return date(value)
    } catch {
      return '—'
    }
  }

  const orderIsDirty = order => {
    const draft = drafts[order.id]
    if (!draft) return false

    return (
      String(draft.customer_name || '').trim() !== String(order.customer_name || '').trim() ||
      String(draft.phone || '').trim() !== String(order.customer_phone || '').trim() ||
      (draft.city || '') !== (order.city || '') ||
      String(draft.address || '').trim() !== String(order.address || '').trim() ||
      (draft.offer_id || '') !== (order.offer_id || '') ||
      String(draft.call_note || '').trim() !== String(order.call_note || '').trim()
    )
  }

  const statusClass = value => {
    if (value === 'CONFIRMED' || value === 'READY' || value === 'DELIVERED') return 'ok'
    if (value === 'BLACKLIST' || value === 'CANCELLED' || value === 'WRONG_NUMBER') return 'bad'
    if (value === 'NO_ANSWER' || value === 'VOICEMAIL' || value === 'BUSY' || value === 'CALLBACK') return 'warn'
    if (LOCKED_DELIVERY.has(value)) return 'sent'
    return 'neutral'
  }

  return (
    <div className="tw-agent" dir={isAr ? 'rtl' : 'ltr'}>
      <section className="tw-head">
        <div>
          <span className="tw-kicker">COD OPS · CALL CENTER</span>
          <h1>{L('Order confirmation workspace', 'مساحة تأكيد الطلبات')}</h1>
          <p>
            {L(
              'Edit customer information, select product offers, record call outcomes and send confirmed orders to delivery.',
              'عدّل بيانات العميل، اختر العرض، سجّل نتيجة المكالمة وأرسل الطلبات المؤكدة إلى التوصيل.'
            )}
          </p>
        </div>
        <div className="tw-head-actions">
          <div className="tw-assigned-total">
            <span>{L('Assigned orders', 'الطلبات المسندة')}</span>
            <strong>{board.counts.all}</strong>
          </div>
          <button type="button" className="tw-primary-btn" onClick={loadManualMeta}>
            + {L('New order', 'طلب جديد')}
          </button>
        </div>
      </section>

      <section className="tw-kpis">
        {kpis.map(([label, count, tone]) => (
          <div className={`tw-kpi ${tone}`} key={tone}>
            <span>{label}</span>
            <strong>{count}</strong>
          </div>
        ))}
      </section>

      {error && <div className="tw-alert error">{error}</div>}

      {notice && (
        <div className="tw-alert success">
          <span>✓ {notice}</span>
          <button type="button" onClick={() => setNotice('')}>×</button>
        </div>
      )}

      {bulkResult && (
        <div className={`tw-alert ${bulkResult.failed ? 'warning' : 'success'}`}>
          <div>
            <strong>{bulkResult.sent} {L('sent', 'تم إرسالها')}</strong>
            {' · '}
            <span>{bulkResult.failed} {L('failed', 'فشلت')}</span>
            {bulkResult.failures.length > 0 && (
              <small>
                {' — '}
                {bulkResult.failures.map(item => item.error).join(' · ')}
              </small>
            )}
          </div>
          <button type="button" onClick={() => setBulkResult(null)}>×</button>
        </div>
      )}

      <section className="tw-control-panel">
        <div className="tw-tabs">
          {tabs.map(([key, label, count]) => (
            <button
              type="button"
              key={key}
              className={bucket === key ? 'tw-tab active' : 'tw-tab'}
              onClick={() => {
                setBucket(key)
                setProductId('')
                setSelectedIds([])
                setSearch('')
              }}
            >
              <span>{label}</span>
              <b>{count}</b>
            </button>
          ))}
        </div>

        <div className="tw-toolbar">
          <div className="tw-search">
            <span>⌕</span>
            <input
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder={L(
                'Search name, phone, city, order or product...',
                'ابحث بالاسم أو الهاتف أو المدينة أو رقم الطلب أو المنتج...'
              )}
            />
            {search && (
              <button type="button" onClick={() => setSearch('')}>×</button>
            )}
          </div>

          <button
            type="button"
            className="tw-secondary-btn"
            onClick={() => loadBoard(bucket, productId)}
            disabled={loading}
          >
            ↻ {L('Refresh', 'تحديث')}
          </button>

          {bucket === 'READY' && readyVisible.length > 0 && (
            <button type="button" className="tw-secondary-btn" onClick={selectAllReady}>
              {readyVisible.every(order => selectedIds.includes(order.id))
                ? L('Clear selection', 'إلغاء التحديد')
                : `${L('Select all ready', 'تحديد كل الجاهز')} (${readyVisible.length})`}
            </button>
          )}
        </div>

        <div className="tw-products-head">
          <div>
            <strong>{L('Products', 'المنتجات')}</strong>
            <span>{currentBucketCount} {L('orders in this stage', 'طلباً في هذه المرحلة')}</span>
          </div>
        </div>

        <div className="tw-product-strip">
          <button
            type="button"
            className={!productId ? 'tw-product-filter active' : 'tw-product-filter'}
            onClick={() => setProductId('')}
          >
            <span>{L('All products', 'كل المنتجات')}</span>
            <b>{currentBucketCount}</b>
          </button>

          {board.products.map(product => (
            <button
              type="button"
              key={product.id}
              className={productId === product.id ? 'tw-product-filter active' : 'tw-product-filter'}
              onClick={() => setProductId(product.id)}
            >
              <span>{product.name}</span>
              <small>{product.sku}</small>
              <b>{product.count}</b>
            </button>
          ))}
        </div>
      </section>

      <div className="tw-list-head">
        <div>
          <h2>{tabs.find(item => item[0] === bucket)?.[1]}</h2>
          <p>{filteredOrders.length} {L('orders shown', 'طلبات ظاهرة')}</p>
        </div>
      </div>

      {loading ? (
        <div className="tw-empty">
          <div className="tw-loader" />
          <strong>{L('Loading orders...', 'جاري تحميل الطلبات...')}</strong>
        </div>
      ) : filteredOrders.length === 0 ? (
        <div className="tw-empty">
          <div className="tw-empty-icon">✓</div>
          <h3>{L('No orders in this view', 'لا توجد طلبات في هذه القائمة')}</h3>
          <p>{L('Choose another stage or product filter.', 'اختر مرحلة أو منتجاً آخر.')}</p>
        </div>
      ) : (
        <section className="tw-order-grid">
          {filteredOrders.map(order => {
            const draft = drafts[order.id] || draftFromOrder(order)
            const offers = order.available_offers || []
            const selectedOffer = offers.find(offer => offer.id === draft.offer_id)
            const currentOfferUnavailable =
              order.offer_id && !offers.some(offer => offer.id === order.offer_id)
            const editable = !!order.editable && !LOCKED_DELIVERY.has(order.delivery_status)
            const dirty = orderIsDirty(order)
            const blacklisted = order.call_status === 'BLACKLIST'
            const ready = order.call_status === 'CONFIRMED' && order.delivery_status === 'READY'
            const checked = selectedIds.includes(order.id)
            const previewTotal = selectedOffer?.price ?? order.total_price
            const previewQty = selectedOffer?.quantity ?? order.quantity ?? 1

            return (
              <article
                className={`tw-order-card${blacklisted ? ' blacklist' : ''}${checked ? ' selected' : ''}`}
                key={order.id}
              >
                <div className="tw-order-top">
                  <div className="tw-order-id-wrap">
                    {bucket === 'READY' && ready && (
                      <label className="tw-check">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleSelected(order.id)}
                        />
                        <span />
                      </label>
                    )}
                    <div>
                      <span className="tw-mini-label">{L('Order', 'الطلب')}</span>
                      <strong className="tw-order-number">{order.order_number}</strong>
                      <small>{formatDate(order.created_at)}</small>
                    </div>
                  </div>

                  <div className="tw-status-stack">
                    <span className={`tw-status ${statusClass(order.call_status)}`}>
                      {statusLabel(order.call_status)}
                    </span>
                    {order.delivery_status && order.delivery_status !== 'NOT_READY' && (
                      <span className={`tw-status ${statusClass(order.delivery_status)}`}>
                        {statusLabel(order.delivery_status)}
                      </span>
                    )}
                  </div>
                </div>

                {blacklisted && (
                  <div className="tw-blacklist-box">
                    <strong>{L('Digylog blacklist', 'القائمة السوداء في Digylog')}</strong>
                    <span>
                      {order.delivery_error ||
                        L(
                          'Correct the customer phone or delivery information, save, then retry.',
                          'صحح رقم الهاتف أو بيانات التوصيل، احفظ التعديلات ثم أعد الإرسال.'
                        )}
                    </span>
                  </div>
                )}

                <div className="tw-customer-summary">
                  <div>
                    <span className="tw-mini-label">{L('Customer', 'العميل')}</span>
                    <strong>{order.customer_name || '—'}</strong>
                    <a href={`tel:${order.customer_phone || ''}`} dir="ltr">
                      {order.customer_phone || '—'}
                    </a>
                  </div>
                  <div className="tw-total-box">
                    <span>{L('Total', 'المجموع')}</span>
                    <strong>{money(previewTotal, order.currency)}</strong>
                    <small>× {previewQty}</small>
                  </div>
                </div>

                <div className="tw-quick-actions">
                  <a className="call" href={`tel:${order.customer_phone || ''}`}>
                    <b>☎</b>
                    <span>{L('Call', 'اتصال')}</span>
                  </a>
                  <a
                    className="whatsapp"
                    href={`https://wa.me/${phoneForWhatsApp(order.customer_phone)}`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    <b>W</b>
                    <span>WhatsApp</span>
                  </a>
                </div>

                <div className="tw-product-box">
                  <div className="tw-product-avatar">
                    {order.product_name ? order.product_name.charAt(0).toUpperCase() : 'P'}
                  </div>
                  <div className="tw-product-main">
                    <span>{L('Product', 'المنتج')}</span>
                    <strong>{order.product_name || '—'}</strong>
                    <small>{order.product_sku || '—'} · {order.store_name || '—'}</small>
                  </div>
                  <div className="tw-product-price">
                    <span>{L('Qty', 'الكمية')}</span>
                    <strong>× {previewQty}</strong>
                  </div>
                </div>

                {editable ? (
                  <>
                    <div className="tw-edit-grid">
                      <label className="tw-card-field">
                        <span>{L('Customer name', 'اسم العميل')}</span>
                        <input
                          value={draft.customer_name}
                          onChange={e => setDraftField(order.id, 'customer_name', e.target.value)}
                        />
                      </label>

                      <label className="tw-card-field">
                        <span>{L('Phone', 'الهاتف')}</span>
                        <input
                          dir="ltr"
                          value={draft.phone}
                          onChange={e => setDraftField(order.id, 'phone', e.target.value)}
                        />
                      </label>
                    </div>

                    <div className="tw-offers-section">
                      <div className="tw-section-title">
                        <strong>{L('Offer', 'العرض')}</strong>
                        <span>{L('Price and quantity come from Product Offers', 'السعر والكمية من عروض المنتج')}</span>
                      </div>

                      <div className="tw-offer-list">
                        {offers.map(offer => (
                          <button
                            type="button"
                            key={offer.id}
                            className={draft.offer_id === offer.id ? 'tw-offer active' : 'tw-offer'}
                            onClick={() => setDraftField(order.id, 'offer_id', offer.id)}
                          >
                            <span>{offer.name}</span>
                            <small>× {offer.quantity}</small>
                            <strong>{money(offer.price, order.currency)}</strong>
                          </button>
                        ))}

                        {currentOfferUnavailable && (
                          <div className="tw-offer unavailable">
                            <span>{order.offer_name || L('Old offer', 'عرض قديم')}</span>
                            <small>{L('Inactive', 'غير نشط')}</small>
                            <strong>{money(order.offer_price || order.total_price, order.currency)}</strong>
                          </div>
                        )}

                        {offers.length === 0 && !currentOfferUnavailable && (
                          <div className="tw-no-offer">
                            {L('No active offers for this product.', 'لا توجد عروض نشطة لهذا المنتج.')}
                          </div>
                        )}
                      </div>
                    </div>

                    <div className="tw-edit-grid tw-location-grid">
                      <div className="tw-card-city">
                        <CitySelect
                          value={draft.city}
                          onChange={city => setDraftField(order.id, 'city', city)}
                          label={L('Digylog city', 'مدينة Digylog')}
                          placeholder={L('Search Digylog city...', 'ابحث عن مدينة Digylog...')}
                          required={false}
                        />
                      </div>

                      <label className="tw-card-field">
                        <span>{L('Address', 'العنوان')}</span>
                        <textarea
                          rows="2"
                          value={draft.address}
                          onChange={e => setDraftField(order.id, 'address', e.target.value)}
                          placeholder={L('Full delivery address...', 'العنوان الكامل للتوصيل...')}
                        />
                      </label>
                    </div>

                    <label className="tw-card-field tw-note-field">
                      <span>{L('Agent note', 'ملاحظة الموظف')}</span>
                      <textarea
                        rows="2"
                        value={draft.call_note}
                        onChange={e => setDraftField(order.id, 'call_note', e.target.value)}
                        placeholder={L('Write call notes...', 'اكتب ملاحظات المكالمة...')}
                      />
                    </label>

                    {!blacklisted && (
                      <div className="tw-outcome-section">
                        <div className="tw-section-title">
                          <strong>{L('Call result', 'نتيجة المكالمة')}</strong>
                          <span>
                            {L(
                              'The order moves automatically to the correct stage.',
                              'سينتقل الطلب تلقائياً إلى المرحلة المناسبة.'
                            )}
                          </span>
                        </div>

                        <div className="tw-outcomes">
                          <button
                            type="button"
                            className="confirm"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'CONFIRMED')}
                          >
                            ✓ {L('Confirmed', 'مؤكد')}
                          </button>
                          <button
                            type="button"
                            className="follow"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'NO_ANSWER')}
                          >
                            {L('No answer', 'لا يجيب')}
                          </button>
                          <button
                            type="button"
                            className="follow"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'VOICEMAIL')}
                          >
                            {L('Voicemail', 'صندوق صوتي')}
                          </button>
                          <button
                            type="button"
                            className="follow"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'BUSY')}
                          >
                            {L('Busy', 'مشغول')}
                          </button>
                          <button
                            type="button"
                            className="callback"
                            disabled={savingId === order.id}
                            onClick={() => openCallback(order)}
                          >
                            ↻ {L('Schedule follow-up', 'جدولة متابعة')}
                          </button>
                          <button
                            type="button"
                            className="closed"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'CANCELLED')}
                          >
                            {L('Cancelled', 'ملغى')}
                          </button>
                          <button
                            type="button"
                            className="closed"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'WRONG_NUMBER')}
                          >
                            {L('Wrong number', 'رقم خاطئ')}
                          </button>
                          <button
                            type="button"
                            className="closed"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'DUPLICATE')}
                          >
                            {L('Duplicate', 'طلب مكرر')}
                          </button>
                          <button
                            type="button"
                            className="closed"
                            disabled={savingId === order.id}
                            onClick={() => saveOrder(order, 'NOT_INTERESTED')}
                          >
                            {L('Not interested', 'غير مهتم')}
                          </button>
                        </div>
                      </div>
                    )}

                    <div className="tw-card-footer">
                      <div className="tw-attempts">
                        <strong>{order.attempt_count || 0}</strong>
                        <span>{L('call attempts', 'محاولات اتصال')}</span>
                        {order.last_attempt && (
                          <small>
                            {statusLabel(order.last_attempt.outcome)} · {formatDate(order.last_attempt.created_at)}
                          </small>
                        )}
                      </div>

                      <div className="tw-footer-actions">
                        {dirty && <span className="tw-unsaved">{L('Unsaved changes', 'تعديلات غير محفوظة')}</span>}
                        <button
                          type="button"
                          className="tw-save-btn"
                          disabled={savingId === order.id}
                          onClick={() => saveOrder(order)}
                        >
                          {savingId === order.id
                            ? L('Saving...', 'جاري الحفظ...')
                            : L('Save changes', 'حفظ التعديلات')}
                        </button>
                      </div>
                    </div>

                    {(ready || blacklisted) && (
                      <button
                        type="button"
                        className={blacklisted ? 'tw-dispatch-btn retry' : 'tw-dispatch-btn'}
                        disabled={dispatchingId === order.id}
                        onClick={() => dispatchDigylog(order)}
                      >
                        {dispatchingId === order.id
                          ? L('Sending...', 'جاري الإرسال...')
                          : blacklisted
                            ? L('Retry send to Digylog', 'إعادة الإرسال إلى Digylog')
                            : L('Send to Digylog', 'إرسال إلى Digylog')}
                      </button>
                    )}
                  </>
                ) : (
                  <div className="tw-readonly-block">
                    <div>
                      <span>{L('Offer', 'العرض')}</span>
                      <strong>{order.offer_name || '—'} · × {order.quantity || 1}</strong>
                    </div>
                    <div>
                      <span>{L('City', 'المدينة')}</span>
                      <strong>{order.city || '—'}</strong>
                    </div>
                    <div className="wide">
                      <span>{L('Address', 'العنوان')}</span>
                      <strong>{order.address || '—'}</strong>
                    </div>
                    <div className="wide">
                      <span>{L('Agent note', 'ملاحظة الموظف')}</span>
                      <strong>{order.call_note || '—'}</strong>
                    </div>
                    <div className="wide lock-note">
                      {L(
                        'This order was already sent to delivery. Customer/shipping fields are locked to avoid differences with Digylog.',
                        'تم إرسال هذا الطلب إلى التوصيل. تم قفل بيانات العميل والشحن لتجنب اختلافها عن بيانات Digylog.'
                      )}
                    </div>
                  </div>
                )}

                <div className="tw-card-meta">
                  <span>{order.source || '—'}</span>
                  {order.delivery_tracking && (
                    <span dir="ltr">{L('Tracking', 'التتبع')}: {order.delivery_tracking}</span>
                  )}
                </div>
              </article>
            )
          })}
        </section>
      )}

      {selectedIds.length > 0 && (
        <div className="tw-bulk-bar">
          <div>
            <span>{L('Selected ready orders', 'الطلبات الجاهزة المحددة')}</span>
            <strong>{selectedIds.length}</strong>
          </div>
          <div>
            <button
              type="button"
              className="tw-secondary-btn"
              disabled={bulkBusy}
              onClick={() => setSelectedIds([])}
            >
              {L('Clear', 'إلغاء التحديد')}
            </button>
            <button
              type="button"
              className="tw-bulk-send"
              disabled={bulkBusy}
              onClick={bulkDispatch}
            >
              {bulkBusy
                ? L('Sending...', 'جاري الإرسال...')
                : `${L('Send selected to Digylog', 'إرسال المحدد إلى Digylog')} (${selectedIds.length})`}
            </button>
          </div>
        </div>
      )}

      <Modal
        open={manualOpen}
        title={L('Add new order', 'إضافة طلب جديد')}
        onClose={() => setManualOpen(false)}
        wide
      >
        {manualProducts.length === 0 ? (
          <div className="empty">
            {L('No products are assigned to your account.', 'لا توجد منتجات مسندة إلى حسابك.')}
          </div>
        ) : (
          <form className="tw-modal-form" onSubmit={createManualOrder}>
            <div className="tw-modal-grid">
              <label className="tw-card-field">
                <span>{L('Product', 'المنتج')}</span>
                <select
                  value={manual.product_id}
                  onChange={e => changeManualProduct(e.target.value)}
                >
                  {manualProducts.map(product => (
                    <option key={product.id} value={product.id}>
                      {product.name} — {product.sku}
                    </option>
                  ))}
                </select>
              </label>

              <div className="tw-card-field full">
                <span>{L('Offer', 'العرض')}</span>
                <div className="tw-offer-list modal-offers">
                  {(manualProduct?.offers || []).map(offer => (
                    <button
                      type="button"
                      key={offer.id}
                      className={manual.offer_id === offer.id ? 'tw-offer active' : 'tw-offer'}
                      onClick={() => setManual(current => ({ ...current, offer_id: offer.id }))}
                    >
                      <span>{offer.name}</span>
                      <small>× {offer.quantity}</small>
                      <strong>{money(offer.price, manualProduct?.currency || 'MAD')}</strong>
                    </button>
                  ))}
                </div>
              </div>

              <label className="tw-card-field">
                <span>{L('Customer name', 'اسم العميل')}</span>
                <input
                  required
                  value={manual.customer_name}
                  onChange={e => setManual(current => ({ ...current, customer_name: e.target.value }))}
                />
              </label>

              <label className="tw-card-field">
                <span>{L('Phone', 'الهاتف')}</span>
                <input
                  required
                  dir="ltr"
                  value={manual.phone}
                  onChange={e => setManual(current => ({ ...current, phone: e.target.value }))}
                />
              </label>

              <div className="tw-card-city">
                <CitySelect
                  value={manual.city}
                  onChange={city => setManual(current => ({ ...current, city }))}
                  label={L('Digylog city', 'مدينة Digylog')}
                  placeholder={L('Search Digylog city...', 'ابحث عن مدينة Digylog...')}
                  required
                />
              </div>

              <label className="tw-card-field">
                <span>{L('Address', 'العنوان')}</span>
                <textarea
                  rows="3"
                  value={manual.address}
                  onChange={e => setManual(current => ({ ...current, address: e.target.value }))}
                />
              </label>

              <label className="tw-card-field full">
                <span>{L('Note', 'ملاحظة')}</span>
                <textarea
                  rows="3"
                  value={manual.call_note}
                  onChange={e => setManual(current => ({ ...current, call_note: e.target.value }))}
                />
              </label>

              <div className="tw-manual-total full">
                <span>{L('Order total', 'إجمالي الطلب')}</span>
                <strong>
                  {manualOffer
                    ? money(manualOffer.price, manualProduct?.currency || 'MAD')
                    : '—'}
                </strong>
                <small>
                  {manualOffer
                    ? `${manualOffer.name} · × ${manualOffer.quantity}`
                    : L('Select an offer', 'اختر عرضاً')}
                </small>
              </div>
            </div>

            <div className="form-actions">
              <button type="button" className="btn secondary" onClick={() => setManualOpen(false)}>
                {L('Cancel', 'إلغاء')}
              </button>
              <button className="btn" disabled={savingManual || !manualOffer}>
                {savingManual ? L('Creating...', 'جاري الإنشاء...') : L('Create order', 'إنشاء الطلب')}
              </button>
            </div>
          </form>
        )}
      </Modal>

      <Modal
        open={callbackOpen}
        title={L('Schedule follow-up', 'جدولة متابعة')}
        onClose={() => setCallbackOpen(false)}
      >
        <form className="tw-modal-form" onSubmit={saveCallback}>
          <div className="tw-modal-grid one">
            <label className="tw-card-field">
              <span>{L('Date & time', 'التاريخ والوقت')}</span>
              <input
                type="datetime-local"
                required
                value={callbackAt}
                onChange={e => setCallbackAt(e.target.value)}
              />
            </label>
            <label className="tw-card-field">
              <span>{L('Note', 'ملاحظة')}</span>
              <textarea
                rows="4"
                value={callbackNote}
                onChange={e => setCallbackNote(e.target.value)}
              />
            </label>
          </div>

          <div className="form-actions">
            <button type="button" className="btn secondary" onClick={() => setCallbackOpen(false)}>
              {L('Cancel', 'إلغاء')}
            </button>
            <button className="btn" disabled={callbackBusy}>
              {callbackBusy ? L('Saving...', 'جاري الحفظ...') : L('Schedule', 'جدولة')}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}

