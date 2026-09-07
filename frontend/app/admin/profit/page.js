'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, money } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import DateRange from '../../../components/DateRange'
import Modal from '../../../components/Modal'

const PAGE_SIZE = 20

function todayISO() {
  const d = new Date()
  const offset = d.getTimezoneOffset()
  return new Date(d.getTime() - offset * 60000).toISOString().slice(0, 10)
}

function qs(period, storeId, productId) {
  const q = new URLSearchParams()
  q.set('range', period.range || 'today')
  if (period.from_date) q.set('from_date', period.from_date)
  if (period.to_date) q.set('to_date', period.to_date)
  if (storeId) q.set('store_id', storeId)
  if (productId) q.set('product_id', productId)
  return q
}

function num(value, digits = 2) {
  const n = Number(value || 0)
  return Number.isFinite(n) ? n.toFixed(digits) : '0.00'
}

function Metric({ label, value, note, tone = '' }) {
  return (
    <div className={`profit-kpi ${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note || '\u00A0'}</small>
    </div>
  )
}

export default function ProfitPage() {
  const { t } = useI18n()

  const [period, setPeriod] = useState({ range: 'today' })
  const [storeId, setStoreId] = useState('')
  const [productId, setProductId] = useState('')

  const [stores, setStores] = useState([])
  const [products, setProducts] = useState([])
  const [dashboard, setDashboard] = useState(null)
  const [rows, setRows] = useState([])

  const [spendRows, setSpendRows] = useState([])
  const [spendTotal, setSpendTotal] = useState(0)
  const [spendPage, setSpendPage] = useState(1)

  const [modalOpen, setModalOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState({
    store_id: '',
    product_id: '',
    spend_date: todayISO(),
    amount: '',
    platform: 'META',
    campaign_name: '',
    note: ''
  })

  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)

  const filteredProducts = useMemo(
    () => storeId
      ? products.filter(p => p.store_id === storeId)
      : products,
    [products, storeId]
  )

  const modalProducts = useMemo(
    () => products.filter(p => p.store_id === form.store_id),
    [products, form.store_id]
  )

  const displayMoney = value =>
    dashboard?.currency === 'MIXED'
      ? '—'
      : money(value || 0, dashboard?.currency || 'MAD')

  const loadMeta = async () => {
    const [s, p] = await Promise.all([
      api('/stores'),
      api('/products')
    ])
    setStores(s)
    setProducts(p)
  }

  const loadMetrics = async () => {
    try {
      const q = qs(period, storeId, productId)
      const [d, p] = await Promise.all([
        api(`/profit/dashboard?${q}`),
        api(`/profit/products?${q}`)
      ])
      setDashboard(d)
      setRows(
        [...(p || [])].sort(
          (a, b) => Number(b.net_profit || 0) - Number(a.net_profit || 0)
        )
      )
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }

  const loadSpend = async (page = spendPage) => {
    try {
      const q = qs(period, storeId, productId)
      q.set('limit', String(PAGE_SIZE))
      q.set('offset', String((page - 1) * PAGE_SIZE))
      const r = await api(`/profit/ad-spend?${q}`)
      setSpendRows(r.items || [])
      setSpendTotal(r.total || 0)
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    loadMeta().catch(e => setError(e.message))
  }, [])

  useEffect(() => {
    setSpendPage(1)
    loadMetrics()
    loadSpend(1)
  }, [period, storeId, productId])

  useEffect(() => {
    if (spendPage > 1) loadSpend(spendPage)
  }, [spendPage])

  const onStoreChange = value => {
    setStoreId(value)
    if (
      productId &&
      !products.some(
        p => p.id === productId && (!value || p.store_id === value)
      )
    ) {
      setProductId('')
    }
  }

  const openCreate = () => {
    const s = storeId || stores[0]?.id || ''
    const candidates = products.filter(p => !s || p.store_id === s)
    setEditing(null)
    setForm({
      store_id: s,
      product_id:
        productId && candidates.some(p => p.id === productId)
          ? productId
          : candidates[0]?.id || '',
      spend_date: todayISO(),
      amount: '',
      platform: 'META',
      campaign_name: '',
      note: ''
    })
    setModalOpen(true)
  }

  const openEdit = row => {
    setEditing(row)
    setForm({
      store_id: row.store_id,
      product_id: row.product_id,
      spend_date: row.spend_date,
      amount: row.amount,
      platform: row.platform || 'META',
      campaign_name: row.campaign_name || '',
      note: row.note || ''
    })
    setModalOpen(true)
  }

  const changeModalStore = value => {
    const candidates = products.filter(p => p.store_id === value)
    setForm(f => ({
      ...f,
      store_id: value,
      product_id: candidates.some(p => p.id === f.product_id)
        ? f.product_id
        : candidates[0]?.id || ''
    }))
  }

  const refresh = async (page = spendPage) => {
    await Promise.all([loadMetrics(), loadSpend(page)])
  }

  const saveSpend = async e => {
    e.preventDefault()
    setSaving(true)
    setError('')
    setSuccess('')

    try {
      if (editing) {
        await api(`/profit/ad-spend/${editing.id}`, {
          method: 'PATCH',
          body: {
            spend_date: form.spend_date,
            amount: Number(form.amount),
            platform: form.platform,
            campaign_name: form.campaign_name || null,
            note: form.note || null
          }
        })
      } else {
        await api('/profit/ad-spend', {
          method: 'POST',
          body: {
            store_id: form.store_id,
            product_id: form.product_id,
            spend_date: form.spend_date,
            amount: Number(form.amount),
            platform: form.platform,
            campaign_name: form.campaign_name || null,
            note: form.note || null
          }
        })
      }

      setModalOpen(false)
      setEditing(null)
      setSpendPage(1)
      setSuccess(editing ? t('Ad spend updated.') : t('Ad spend added.'))
      await refresh(1)
    } catch (e2) {
      setError(e2.message)
    } finally {
      setSaving(false)
    }
  }

  const removeSpend = async row => {
    if (!window.confirm(t('Delete this ad spend entry?'))) return

    try {
      await api(`/profit/ad-spend/${row.id}`, { method: 'DELETE' })
      setSuccess(t('Ad spend deleted.'))
      const next = spendRows.length === 1 && spendPage > 1
        ? spendPage - 1
        : spendPage
      setSpendPage(next)
      await refresh(next)
    } catch (e) {
      setError(e.message)
    }
  }

  const pages = Math.max(1, Math.ceil(spendTotal / PAGE_SIZE))

  return (
    <div className="profit-page">
      <div className="profit-hero">
        <div>
          <span>COD OPS · FINANCE</span>
          <h1>{t('Profit Center')}</h1>
          <p>
            {t('Realized profit based on delivered orders, product costs, ads, commissions and delivery costs.')}
          </p>
        </div>

        <button className="btn profit-add-btn" onClick={openCreate}>
          + {t('Add Ad Spend')}
        </button>
      </div>

      <div className="profit-filters">
        <DateRange value={period} onChange={setPeriod} />

        <select value={storeId} onChange={e => onStoreChange(e.target.value)}>
          <option value="">{t('All Stores')}</option>
          {stores.map(s => (
            <option key={s.id} value={s.id}>{s.name}</option>
          ))}
        </select>

        <select value={productId} onChange={e => setProductId(e.target.value)}>
          <option value="">{t('All Products')}</option>
          {filteredProducts.map(p => (
            <option key={p.id} value={p.id}>{p.name} — {p.sku}</option>
          ))}
        </select>
      </div>

      {error && <div className="error">{error}</div>}
      {success && <div className="success-box">{success}</div>}

      {dashboard?.currency_warning && (
        <div className="profit-warning">
          <strong>{t('Currency warning')}</strong>
          <span>{t('Select one store to view valid combined financial totals.')}</span>
        </div>
      )}

      <div className="profit-kpis">
        <Metric
          label={t('Delivered Revenue')}
          value={displayMoney(dashboard?.revenue)}
          note={`${dashboard?.delivered || 0} ${t('delivered orders')}`}
          tone="blue"
        />
        <Metric
          label={t('Net Profit')}
          value={displayMoney(dashboard?.net_profit)}
          note={`${num(dashboard?.profit_margin)}% ${t('margin')}`}
          tone={Number(dashboard?.net_profit || 0) >= 0 ? 'green' : 'red'}
        />
        <Metric
          label={t('Ad Spend')}
          value={displayMoney(dashboard?.ad_spend)}
          note={`${num(dashboard?.roas)}x ROAS`}
          tone="purple"
        />
        <Metric
          label={t('Total Cost')}
          value={displayMoney(dashboard?.total_cost)}
          note={t('All tracked costs')}
          tone="amber"
        />
        <Metric
          label={t('Product Cost')}
          value={displayMoney(dashboard?.product_cost)}
          note={`${dashboard?.units_delivered || 0} ${t('units delivered')}`}
        />
        <Metric
          label={t('Packaging Cost')}
          value={displayMoney(dashboard?.packaging_cost)}
          note={t('Per delivered order')}
        />
        <Metric
          label={t('Agent Cost')}
          value={displayMoney(dashboard?.agent_cost)}
          note={t('Confirmation commissions')}
        />
        <Metric
          label={t('Delivery Cost')}
          value={displayMoney(dashboard?.delivery_cost)}
          note={t('Seller-paid delivery only')}
        />
      </div>

      <div className="profit-mini-grid">
        {[
          ['ROAS', `${num(dashboard?.roas)}x`],
          [t('Profit Margin'), `${num(dashboard?.profit_margin)}%`],
          [t('CPA Confirmed'), dashboard?.currency === 'MIXED' ? '—' : money(dashboard?.cpa_confirmed || 0, dashboard?.currency || 'MAD')],
          [t('CPA Delivered'), dashboard?.currency === 'MIXED' ? '—' : money(dashboard?.cpa_delivered || 0, dashboard?.currency || 'MAD')],
          [t('Confirmed'), dashboard?.confirmed || 0],
          [t('Delivered'), dashboard?.delivered || 0],
          [t('Refused'), dashboard?.refused || 0],
          [t('Returned'), dashboard?.returned || 0]
        ].map(([label, value]) => (
          <div className="profit-mini" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <div className="panel profit-panel">
        <div className="panel-head">
          <div>
            <h2>{t('Product Profitability')}</h2>
            <p>{t('Delivered revenue and tracked costs product by product.')}</p>
          </div>
        </div>

        <div className="table-wrap">
          <table className="table profit-table">
            <thead>
              <tr>
                <th>{t('Product')}</th>
                <th>{t('Delivered')}</th>
                <th>{t('Units')}</th>
                <th>{t('Revenue')}</th>
                <th>{t('Ad Spend')}</th>
                <th>{t('Product Cost')}</th>
                <th>{t('Packaging')}</th>
                <th>{t('Agent Cost')}</th>
                <th>{t('Delivery Cost')}</th>
                <th>{t('Total Cost')}</th>
                <th>{t('Net Profit')}</th>
                <th>ROAS</th>
                <th>{t('Margin')}</th>
              </tr>
            </thead>

            <tbody>
              {rows.map(r => (
                <tr key={r.product_id}>
                  <td>
                    <div className="profit-product">
                      <div className="profit-product-img">
                        {r.image_url
                          ? <img src={r.image_url} alt={r.name} />
                          : <span>{(r.name || 'P')[0]}</span>}
                      </div>
                      <div>
                        <strong>{r.name}</strong>
                        <small>{r.sku}</small>
                      </div>
                    </div>
                  </td>
                  <td>{r.delivered}</td>
                  <td>{r.units}</td>
                  <td><strong>{money(r.revenue, r.currency)}</strong></td>
                  <td>{money(r.ad_spend, r.currency)}</td>
                  <td>{money(r.product_cost, r.currency)}</td>
                  <td>{money(r.packaging_cost, r.currency)}</td>
                  <td>{money(r.agent_cost, r.currency)}</td>
                  <td>{money(r.delivery_cost, r.currency)}</td>
                  <td>{money(r.total_cost, r.currency)}</td>
                  <td>
                    <strong className={Number(r.net_profit || 0) >= 0 ? 'profit-pos' : 'profit-neg'}>
                      {money(r.net_profit, r.currency)}
                    </strong>
                  </td>
                  <td>{num(r.roas)}x</td>
                  <td>{num(r.margin)}%</td>
                </tr>
              ))}

              {!rows.length && (
                <tr>
                  <td colSpan="13">
                    <div className="empty">{t('No profit data for this period.')}</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel profit-panel">
        <div className="panel-head">
          <div>
            <h2>{t('Ad Spend')}</h2>
            <p>{t('Manual advertising costs used in product profitability calculations.')}</p>
          </div>

          <button className="btn secondary" onClick={openCreate}>
            + {t('Add Ad Spend')}
          </button>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Date')}</th>
                <th>{t('Product')}</th>
                <th>{t('Platform')}</th>
                <th>{t('Campaign')}</th>
                <th>{t('Amount')}</th>
                <th>{t('Note')}</th>
                <th>{t('Actions')}</th>
              </tr>
            </thead>

            <tbody>
              {spendRows.map(r => (
                <tr key={r.id}>
                  <td>{r.spend_date}</td>
                  <td><strong>{r.product_name || '—'}</strong></td>
                  <td><span className="profit-platform">{r.platform}</span></td>
                  <td>{r.campaign_name || '—'}</td>
                  <td><strong>{money(r.amount, r.currency)}</strong></td>
                  <td>{r.note || '—'}</td>
                  <td>
                    <div className="profit-actions">
                      <button className="btn small secondary" onClick={() => openEdit(r)}>
                        {t('Edit')}
                      </button>
                      <button className="btn small danger" onClick={() => removeSpend(r)}>
                        {t('Delete')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}

              {!spendRows.length && (
                <tr>
                  <td colSpan="7">
                    <div className="empty">{t('No ad spend entries in this period.')}</div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {spendTotal > 0 && (
          <div className="profit-pager">
            <span>
              {(spendPage - 1) * PAGE_SIZE + 1}–{Math.min(spendPage * PAGE_SIZE, spendTotal)} / {spendTotal}
            </span>

            <div>
              <button
                disabled={spendPage <= 1}
                onClick={() => setSpendPage(p => Math.max(1, p - 1))}
              >
                ‹
              </button>

              <strong>{spendPage} / {pages}</strong>

              <button
                disabled={spendPage >= pages}
                onClick={() => setSpendPage(p => Math.min(pages, p + 1))}
              >
                ›
              </button>
            </div>
          </div>
        )}
      </div>

      <Modal
        open={modalOpen}
        title={editing ? t('Edit Ad Spend') : t('Add Ad Spend')}
        onClose={() => {
          if (!saving) {
            setModalOpen(false)
            setEditing(null)
          }
        }}
      >
        <form onSubmit={saveSpend}>
          {!editing && (
            <>
              <div className="field">
                <label>{t('Store')}</label>
                <select
                  required
                  value={form.store_id}
                  onChange={e => changeModalStore(e.target.value)}
                >
                  <option value="">{t('Select Store')}</option>
                  {stores.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>

              <div className="field">
                <label>{t('Product')}</label>
                <select
                  required
                  value={form.product_id}
                  onChange={e => setForm({ ...form, product_id: e.target.value })}
                >
                  <option value="">{t('Select Product')}</option>
                  {modalProducts.map(p => (
                    <option key={p.id} value={p.id}>{p.name} — {p.sku}</option>
                  ))}
                </select>
              </div>
            </>
          )}

          {editing && (
            <div className="profit-edit-context">
              <span>{t('Product')}</span>
              <strong>{editing.product_name || '—'}</strong>
            </div>
          )}

          <div className="field">
            <label>{t('Date')}</label>
            <input
              required
              type="date"
              value={form.spend_date}
              onChange={e => setForm({ ...form, spend_date: e.target.value })}
            />
          </div>

          <div className="field">
            <label>{t('Platform')}</label>
            <select
              required
              value={form.platform}
              onChange={e => setForm({ ...form, platform: e.target.value })}
            >
              <option value="META">Meta Ads</option>
              <option value="TIKTOK">TikTok Ads</option>
              <option value="GOOGLE">Google Ads</option>
              <option value="SNAPCHAT">Snapchat Ads</option>
              <option value="OTHER">{t('Other')}</option>
            </select>
          </div>

          <div className="field">
            <label>{t('Amount')}</label>
            <input
              required
              type="number"
              min="0.01"
              step="0.01"
              value={form.amount}
              onChange={e => setForm({ ...form, amount: e.target.value })}
            />
          </div>

          <div className="field">
            <label>{t('Campaign')}</label>
            <input
              value={form.campaign_name}
              onChange={e => setForm({ ...form, campaign_name: e.target.value })}
              placeholder={t('Optional campaign name')}
            />
          </div>

          <div className="field">
            <label>{t('Note')}</label>
            <textarea
              value={form.note}
              onChange={e => setForm({ ...form, note: e.target.value })}
              placeholder={t('Optional note')}
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              disabled={saving}
              onClick={() => {
                setModalOpen(false)
                setEditing(null)
              }}
            >
              {t('Cancel')}
            </button>

            <button className="btn" disabled={saving}>
              {saving
                ? t('Saving...')
                : editing
                  ? t('Save Changes')
                  : t('Add Ad Spend')}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
