'use client'

import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import Modal from '../../../components/Modal'
import StatusBadge from '../../../components/StatusBadge'

const emptyDigylog = {
  name: 'Digylog Morocco',
  store_id: '',
  api_token: '',
  digylog_store: '',
  network: 1,
  port: 1,
  add_status: 1,
  check_duplicate: true,
  api_base_url: 'https://api.digylog.com/api/v2/seller',
  orders_url: 'https://api.digylog.com/api/v2/seller/orders'
}

const emptySheets = {
  name: 'Google Sheets Leads',
  store_id: '',
  sheet_name: 'Sheet1',
  default_product_id: '',
  auto_assign: true
}

function providerLabel(provider) {
  return provider === 'GOOGLE_SHEETS'
    ? 'Google Sheets'
    : 'Digylog'
}

export default function IntegrationsPage() {
  const { t, date } = useI18n()

  const [items, setItems] = useState([])
  const [stores, setStores] = useState([])
  const [products, setProducts] = useState([])
  const [events, setEvents] = useState([])

  const [open, setOpen] = useState(null)

  const [digy, setDigy] = useState(emptyDigylog)
  const [sheets, setSheets] = useState(emptySheets)

  const [editing, setEditing] = useState(null)
  const [editDigy, setEditDigy] = useState(emptyDigylog)
  const [editSheets, setEditSheets] = useState(emptySheets)

  const [script, setScript] = useState('')
  const [scriptOpen, setScriptOpen] = useState(false)
  const [webhook, setWebhook] = useState('')

  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () =>
    Promise.all([
      api('/integrations'),
      api('/stores'),
      api('/products'),
      api('/integrations/events?limit=40')
    ])
      .then(([i, s, p, e]) => {
        setItems(i)
        setStores(s)
        setProducts(p)
        setEvents(e)

        const storeId = s[0]?.id || ''

        setDigy(f => ({
          ...f,
          store_id: f.store_id || storeId
        }))

        setSheets(f => ({
          ...f,
          store_id: f.store_id || storeId
        }))
      })
      .catch(e => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const productsForSheets = useMemo(
    () =>
      products.filter(
        p =>
          p.store_id === sheets.store_id &&
          p.status === 'ACTIVE'
      ),
    [products, sheets.store_id]
  )

  const editProductsForSheets = useMemo(
    () =>
      products.filter(
        p =>
          p.store_id === editSheets.store_id &&
          p.status === 'ACTIVE'
      ),
    [products, editSheets.store_id]
  )

  const flash = message => {
    setSuccess(message)

    setTimeout(() => {
      setSuccess('')
    }, 3500)
  }

  const copy = async text => {
    try {
      await navigator.clipboard.writeText(text)
      flash(t('Copied to clipboard.'))
    } catch (_) {
      setError(
        t(
          'Could not copy automatically. Select and copy the text manually.'
        )
      )
    }
  }

  const createDigylog = async e => {
    e.preventDefault()

    setSaving(true)
    setError('')

    try {
      await api('/integrations', {
        method: 'POST',
        body: {
          provider: 'DIGYLOG',
          name: digy.name,
          store_id: digy.store_id,
          is_active: true,
          config: {
            digylog_store: digy.digylog_store,
            network: Number(digy.network),
            port: Number(digy.port),
            add_status: Number(digy.add_status),
            check_duplicate: !!digy.check_duplicate,
            api_base_url: digy.api_base_url,
            orders_url: digy.orders_url
          },
          secrets: {
            api_token: digy.api_token
          }
        }
      })

      setOpen(null)

      setDigy({
        ...emptyDigylog,
        store_id: stores[0]?.id || ''
      })

      flash(t('Digylog integration saved.'))

      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const createSheets = async e => {
    e.preventDefault()

    setSaving(true)
    setError('')

    try {
      const row = await api('/integrations', {
        method: 'POST',
        body: {
          provider: 'GOOGLE_SHEETS',
          name: sheets.name,
          store_id: sheets.store_id,
          is_active: true,
          config: {
            sheet_name: sheets.sheet_name,
            default_product_id:
              sheets.default_product_id || null,
            auto_assign: !!sheets.auto_assign
          },
          secrets: {}
        }
      })

      setOpen(null)

      setSheets({
        ...emptySheets,
        store_id: stores[0]?.id || ''
      })

      flash(t('Google Sheets integration saved.'))

      await load()
      await showScript(row)
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const test = async row => {
    setError('')

    try {
      const r = await api(
        `/integrations/${row.id}/test`,
        {
          method: 'POST'
        }
      )

      if (r.ok) {
        flash(r.message || t('Connection OK'))
      } else {
        setError(
          r.message ||
          t('Connection test failed')
        )
      }

      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const toggle = async row => {
    setError('')

    try {
      await api(`/integrations/${row.id}`, {
        method: 'PATCH',
        body: {
          is_active: !row.is_active
        }
      })

      flash(
        row.is_active
          ? 'Integration disabled.'
          : 'Integration enabled.'
      )

      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const showWebhook = async row => {
    setError('')

    try {
      const r = await api(
        `/integrations/${row.id}/webhook-config`
      )

      setWebhook(r.webhook_url)
      setScript('')
      setScriptOpen(true)
    } catch (e) {
      setError(e.message)
    }
  }

  const showScript = async row => {
    setError('')

    try {
      const r = await api(
        `/integrations/google-sheets/${row.id}/script`
      )

      setWebhook(r.webhook_url)
      setScript(r.script)
      setScriptOpen(true)
    } catch (e) {
      setError(e.message)
    }
  }

  const openEdit = row => {
    setError('')
    setEditing(row)

    const config = row.config || {}

    if (row.provider === 'DIGYLOG') {
      setEditDigy({
        name: row.name || '',
        store_id: row.store_id || '',
        api_token: '',
        digylog_store:
          config.digylog_store || '',
        network:
          config.network ?? 1,
        port:
          config.port ?? 1,
        add_status:
          config.add_status ?? 1,
        check_duplicate:
          config.check_duplicate !== false,
        api_base_url:
          config.api_base_url ||
          'https://api.digylog.com/api/v2/seller',
        orders_url:
          config.orders_url ||
          'https://api.digylog.com/api/v2/seller/orders'
      })
    } else {
      setEditSheets({
        name: row.name || '',
        store_id: row.store_id || '',
        sheet_name:
          config.sheet_name || 'Sheet1',
        default_product_id:
          config.default_product_id || '',
        auto_assign:
          config.auto_assign !== false
      })
    }
  }

  const closeEdit = () => {
    if (saving) return

    setEditing(null)
    setEditDigy(emptyDigylog)
    setEditSheets(emptySheets)
  }

  const saveEdit = async e => {
    e.preventDefault()

    if (!editing) return

    setSaving(true)
    setError('')

    try {
      if (editing.provider === 'DIGYLOG') {
        const body = {
          name: editDigy.name,
          store_id: editDigy.store_id,
          config: {
            digylog_store:
              editDigy.digylog_store,
            network:
              Number(editDigy.network),
            port:
              Number(editDigy.port),
            add_status:
              Number(editDigy.add_status),
            check_duplicate:
              !!editDigy.check_duplicate,
            api_base_url:
              editDigy.api_base_url,
            orders_url:
              editDigy.orders_url
          }
        }

        if (editDigy.api_token.trim()) {
          body.secrets = {
            api_token:
              editDigy.api_token.trim()
          }
        }

        await api(
          `/integrations/${editing.id}`,
          {
            method: 'PATCH',
            body
          }
        )
      } else {
        await api(
          `/integrations/${editing.id}`,
          {
            method: 'PATCH',
            body: {
              name: editSheets.name,
              store_id:
                editSheets.store_id,
              config: {
                sheet_name:
                  editSheets.sheet_name,
                default_product_id:
                  editSheets.default_product_id ||
                  null,
                auto_assign:
                  !!editSheets.auto_assign
              }
            }
          }
        )
      }

      flash('Integration updated successfully.')

      closeEdit()
      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  const removeIntegration = async row => {
    setError('')

    if (row.is_active) {
      setError(
        `Disable "${row.name}" before deleting it.`
      )
      return
    }

    const ok = window.confirm(
      `Delete "${row.name}"?\n\n` +
      `The integration configuration will be removed.\n` +
      `Orders will not be deleted.\n\n` +
      `This action cannot be undone.`
    )

    if (!ok) return

    setSaving(true)

    try {
      await api(`/integrations/${row.id}`, {
        method: 'DELETE'
      })

      flash(`"${row.name}" deleted.`)

      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('Integrations')}</h1>

          <p>
            {t(
              'Connect delivery and lead sources without hard-coding credentials.'
            )}
          </p>
        </div>

        <div
          style={{
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap'
          }}
        >
          <button
            className="btn"
            onClick={() => setOpen('digylog')}
          >
            {t('+ Connect Digylog')}
          </button>

          <button
            className="btn secondary"
            onClick={() => setOpen('sheets')}
          >
            {t('+ Connect Google Sheets')}
          </button>
        </div>
      </div>

      {error && (
        <div className="error">
          {error}
        </div>
      )}

      {success && (
        <div className="success-box">
          {success}
        </div>
      )}

      <div className="panel">
        <div className="panel-head">
          <h2>{t('Connections')}</h2>

          <span className="badge">
            {items.length} {t('configured')}
          </span>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Provider')}</th>
                <th>{t('Name / Store')}</th>
                <th>{t('Status')}</th>
                <th>{t('Last Test')}</th>
                <th>{t('Actions')}</th>
              </tr>
            </thead>

            <tbody>
              {items.length === 0 && (
                <tr>
                  <td colSpan="5">
                    <div className="empty">
                      {t(
                        'No integration yet. Connect Digylog or Google Sheets above.'
                      )}
                    </div>
                  </td>
                </tr>
              )}

              {items.map(row => {
                const store = stores.find(
                  s => s.id === row.store_id
                )

                return (
                  <tr key={row.id}>
                    <td>
                      <strong>
                        {providerLabel(row.provider)}
                      </strong>

                      <br />

                      <small>
                        {row.provider}
                      </small>
                    </td>

                    <td>
                      {row.name}

                      <br />

                      <small>
                        {store?.name ||
                          t(
                            'All stores / no store'
                          )}
                      </small>
                    </td>

                    <td>
                      <StatusBadge
                        value={
                          row.is_active
                            ? 'ACTIVE'
                            : 'DISABLED'
                        }
                      />
                    </td>

                    <td>
                      {row.last_test_status ? (
                        <>
                          <StatusBadge
                            value={
                              row.last_test_status
                            }
                          />

                          <br />

                          <small>
                            {row.last_test_message ||
                              ''}
                          </small>
                        </>
                      ) : (
                        <StatusBadge value="NOT_TESTED" />
                      )}
                    </td>

                    <td>
                      <div
                        style={{
                          display: 'flex',
                          gap: 6,
                          flexWrap: 'wrap'
                        }}
                      >
                        <button
                          className="btn small"
                          onClick={() =>
                            openEdit(row)
                          }
                        >
                          Edit
                        </button>

                        <button
                          className="btn small secondary"
                          onClick={() => test(row)}
                        >
                          {t('Test')}
                        </button>

                        {row.provider ===
                        'GOOGLE_SHEETS' ? (
                          <button
                            className="btn small secondary"
                            onClick={() =>
                              showScript(row)
                            }
                          >
                            {t('Apps Script')}
                          </button>
                        ) : (
                          <button
                            className="btn small secondary"
                            onClick={() =>
                              showWebhook(row)
                            }
                          >
                            {t('Webhook')}
                          </button>
                        )}

                        <button
                          className={
                            row.is_active
                              ? 'btn small danger'
                              : 'btn small success'
                          }
                          onClick={() =>
                            toggle(row)
                          }
                        >
                          {row.is_active
                            ? t('Disable')
                            : t('Enable')}
                        </button>

                        <button
                          className="btn small danger"
                          disabled={
                            row.is_active || saving
                          }
                          title={
                            row.is_active
                              ? 'Disable integration before deleting'
                              : 'Delete integration'
                          }
                          onClick={() =>
                            removeIntegration(row)
                          }
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <div className="panel-head">
          <h2>
            {t('Recent Integration Events')}
          </h2>

          <span className="badge">
            {t('Troubleshooting log')}
          </span>
        </div>

        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Time')}</th>
                <th>{t('Provider')}</th>
                <th>{t('Direction')}</th>
                <th>{t('Event')}</th>
                <th>{t('Status')}</th>
                <th>{t('Error')}</th>
              </tr>
            </thead>

            <tbody>
              {events.length === 0 && (
                <tr>
                  <td colSpan="6">
                    <div className="empty">
                      {t('No events yet.')}
                    </div>
                  </td>
                </tr>
              )}

              {events.map(e => (
                <tr key={e.id}>
                  <td>
                    {date(e.created_at)}
                  </td>

                  <td>
                    {providerLabel(e.provider)}
                  </td>

                  <td>{e.direction}</td>

                  <td>{e.event_type}</td>

                  <td>
                    <StatusBadge
                      value={e.status}
                    />
                  </td>

                  <td>
                    <small>
                      {e.error || '—'}
                    </small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* CREATE DIGYLOG */}
      <Modal
        open={open === 'digylog'}
        title="Connect Digylog"
        onClose={() => setOpen(null)}
        wide
      >
        <form onSubmit={createDigylog}>
          <div className="form-grid">
            <div className="field">
              <label>
                {t('Connection Name')}
              </label>

              <input
                required
                value={digy.name}
                onChange={e =>
                  setDigy({
                    ...digy,
                    name: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Platform Store')}
              </label>

              <select
                required
                value={digy.store_id}
                onChange={e =>
                  setDigy({
                    ...digy,
                    store_id: e.target.value
                  })
                }
              >
                {stores.map(s => (
                  <option
                    value={s.id}
                    key={s.id}
                  >
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field full">
              <label>
                {t('Digylog API Token')}
              </label>

              <input
                required
                type="password"
                autoComplete="new-password"
                placeholder={t(
                  'Paste the seller API token'
                )}
                value={digy.api_token}
                onChange={e =>
                  setDigy({
                    ...digy,
                    api_token:
                      e.target.value
                  })
                }
              />

              <small>
                {t(
                  'Stored encrypted. It is never returned to the browser after save.'
                )}
              </small>
            </div>

            <div className="field">
              <label>
                {t(
                  'Digylog Store ID / Ref'
                )}
              </label>

              <input
                value={digy.digylog_store}
                onChange={e =>
                  setDigy({
                    ...digy,
                    digylog_store:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Network')}</label>

              <input
                type="number"
                min="1"
                value={digy.network}
                onChange={e =>
                  setDigy({
                    ...digy,
                    network:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Shipping Fee (port)')}
              </label>

              <select
                value={digy.port}
                onChange={e =>
                  setDigy({
                    ...digy,
                    port: e.target.value
                  })
                }
              >
                <option value="1">
                  1 — {t('Customer pays')}
                </option>

                <option value="2">
                  2 — {t('Seller pays')}
                </option>
              </select>
            </div>

            <div className="field">
              <label>
                {t('After Create')}
              </label>

              <select
                value={digy.add_status}
                onChange={e =>
                  setDigy({
                    ...digy,
                    add_status:
                      e.target.value
                  })
                }
              >
                <option value="1">
                  {t('Create & send')}
                </option>

                <option value="0">
                  {t('Create only')}
                </option>
              </select>
            </div>

            <div className="field full">
              <label className="check">
                <input
                  type="checkbox"
                  checked={
                    digy.check_duplicate
                  }
                  onChange={e =>
                    setDigy({
                      ...digy,
                      check_duplicate:
                        e.target.checked
                    })
                  }
                />

                {t(
                  'Ask Digylog to check duplicates'
                )}
              </label>
            </div>

            <div className="field full">
              <label>
                {t('Orders API URL')}
              </label>

              <input
                value={digy.orders_url}
                onChange={e =>
                  setDigy({
                    ...digy,
                    orders_url:
                      e.target.value
                  })
                }
              />
            </div>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() => setOpen(null)}
            >
              {t('Cancel')}
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? t('Saving...')
                : t('Save Digylog')}
            </button>
          </div>
        </form>
      </Modal>

      {/* CREATE SHEETS */}
      <Modal
        open={open === 'sheets'}
        title="Connect Google Sheets"
        onClose={() => setOpen(null)}
        wide
      >
        <form onSubmit={createSheets}>
          <div className="form-grid">
            <div className="field">
              <label>
                {t('Connection Name')}
              </label>

              <input
                required
                value={sheets.name}
                onChange={e =>
                  setSheets({
                    ...sheets,
                    name: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Platform Store')}
              </label>

              <select
                required
                value={sheets.store_id}
                onChange={e =>
                  setSheets({
                    ...sheets,
                    store_id:
                      e.target.value,
                    default_product_id: ''
                  })
                }
              >
                {stores.map(s => (
                  <option
                    value={s.id}
                    key={s.id}
                  >
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>
                {t(
                  'Google Sheet Tab Name'
                )}
              </label>

              <input
                required
                value={sheets.sheet_name}
                onChange={e =>
                  setSheets({
                    ...sheets,
                    sheet_name:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t(
                  'Default Product (optional)'
                )}
              </label>

              <select
                value={
                  sheets.default_product_id
                }
                onChange={e =>
                  setSheets({
                    ...sheets,
                    default_product_id:
                      e.target.value
                  })
                }
              >
                <option value="">
                  {t('Match by SKU')}
                </option>

                {productsForSheets.map(p => (
                  <option
                    key={p.id}
                    value={p.id}
                  >
                    {p.name} — {p.sku}
                  </option>
                ))}
              </select>
            </div>

            <div className="field full">
              <label className="check">
                <input
                  type="checkbox"
                  checked={sheets.auto_assign}
                  onChange={e =>
                    setSheets({
                      ...sheets,
                      auto_assign:
                        e.target.checked
                    })
                  }
                />

                {t(
                  'Smart auto-assign imported leads to eligible agents'
                )}
              </label>
            </div>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() => setOpen(null)}
            >
              {t('Cancel')}
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? t('Saving...')
                : t(
                    'Save & Generate Script'
                  )}
            </button>
          </div>
        </form>
      </Modal>

      {/* EDIT DIGYLOG */}
      <Modal
        open={
          !!editing &&
          editing.provider === 'DIGYLOG'
        }
        title="Edit Digylog"
        onClose={closeEdit}
        wide
      >
        <form onSubmit={saveEdit}>
          <div className="form-grid">
            <div className="field">
              <label>
                {t('Connection Name')}
              </label>

              <input
                required
                value={editDigy.name}
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    name: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Platform Store')}
              </label>

              <select
                required
                value={editDigy.store_id}
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    store_id:
                      e.target.value
                  })
                }
              >
                {stores.map(s => (
                  <option
                    value={s.id}
                    key={s.id}
                  >
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field full">
              <label>
                New Digylog API Token
                (optional)
              </label>

              <input
                type="password"
                autoComplete="new-password"
                placeholder="Leave empty to keep the current token"
                value={editDigy.api_token}
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    api_token:
                      e.target.value
                  })
                }
              />

              <small>
                Current token stays unchanged
                when this field is empty.
              </small>
            </div>

            <div className="field">
              <label>
                {t(
                  'Digylog Store ID / Ref'
                )}
              </label>

              <input
                value={
                  editDigy.digylog_store
                }
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    digylog_store:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Network')}</label>

              <input
                type="number"
                min="1"
                value={editDigy.network}
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    network:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Shipping Fee (port)')}
              </label>

              <select
                value={editDigy.port}
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    port: e.target.value
                  })
                }
              >
                <option value="1">
                  1 — {t('Customer pays')}
                </option>

                <option value="2">
                  2 — {t('Seller pays')}
                </option>
              </select>
            </div>

            <div className="field">
              <label>
                {t('After Create')}
              </label>

              <select
                value={
                  editDigy.add_status
                }
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    add_status:
                      e.target.value
                  })
                }
              >
                <option value="1">
                  {t('Create & send')}
                </option>

                <option value="0">
                  {t('Create only')}
                </option>
              </select>
            </div>

            <div className="field full">
              <label className="check">
                <input
                  type="checkbox"
                  checked={
                    editDigy.check_duplicate
                  }
                  onChange={e =>
                    setEditDigy({
                      ...editDigy,
                      check_duplicate:
                        e.target.checked
                    })
                  }
                />

                {t(
                  'Ask Digylog to check duplicates'
                )}
              </label>
            </div>

            <div className="field full">
              <label>
                {t('Orders API URL')}
              </label>

              <input
                value={editDigy.orders_url}
                onChange={e =>
                  setEditDigy({
                    ...editDigy,
                    orders_url:
                      e.target.value
                  })
                }
              />
            </div>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={closeEdit}
            >
              {t('Cancel')}
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? 'Saving...'
                : 'Save Changes'}
            </button>
          </div>
        </form>
      </Modal>

      {/* EDIT GOOGLE SHEETS */}
      <Modal
        open={
          !!editing &&
          editing.provider ===
            'GOOGLE_SHEETS'
        }
        title="Edit Google Sheets"
        onClose={closeEdit}
        wide
      >
        <form onSubmit={saveEdit}>
          <div className="form-grid">
            <div className="field">
              <label>
                {t('Connection Name')}
              </label>

              <input
                required
                value={editSheets.name}
                onChange={e =>
                  setEditSheets({
                    ...editSheets,
                    name: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Platform Store')}
              </label>

              <select
                required
                value={
                  editSheets.store_id
                }
                onChange={e =>
                  setEditSheets({
                    ...editSheets,
                    store_id:
                      e.target.value,
                    default_product_id: ''
                  })
                }
              >
                {stores.map(s => (
                  <option
                    value={s.id}
                    key={s.id}
                  >
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>
                {t(
                  'Google Sheet Tab Name'
                )}
              </label>

              <input
                required
                value={
                  editSheets.sheet_name
                }
                onChange={e =>
                  setEditSheets({
                    ...editSheets,
                    sheet_name:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t(
                  'Default Product (optional)'
                )}
              </label>

              <select
                value={
                  editSheets.default_product_id
                }
                onChange={e =>
                  setEditSheets({
                    ...editSheets,
                    default_product_id:
                      e.target.value
                  })
                }
              >
                <option value="">
                  {t('Match by SKU')}
                </option>

                {editProductsForSheets.map(
                  p => (
                    <option
                      key={p.id}
                      value={p.id}
                    >
                      {p.name} — {p.sku}
                    </option>
                  )
                )}
              </select>
            </div>

            <div className="field full">
              <label className="check">
                <input
                  type="checkbox"
                  checked={
                    editSheets.auto_assign
                  }
                  onChange={e =>
                    setEditSheets({
                      ...editSheets,
                      auto_assign:
                        e.target.checked
                    })
                  }
                />

                {t(
                  'Smart auto-assign imported leads to eligible agents'
                )}
              </label>
            </div>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={closeEdit}
            >
              {t('Cancel')}
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? 'Saving...'
                : 'Save Changes'}
            </button>
          </div>
        </form>
      </Modal>

      {/* WEBHOOK / SCRIPT */}
      <Modal
        open={scriptOpen}
        title={
          script
            ? 'Google Apps Script'
            : 'Webhook URL'
        }
        onClose={() =>
          setScriptOpen(false)
        }
        wide
      >
        <div className="field full">
          <label>
            {t(
              'Webhook URL — keep it private'
            )}
          </label>

          <textarea
            className="code-box"
            readOnly
            value={webhook}
          />

          <div style={{ marginTop: 8 }}>
            <button
              className="btn small secondary"
              onClick={() => copy(webhook)}
            >
              {t('Copy Webhook')}
            </button>
          </div>
        </div>

        {script && (
          <div
            className="field full"
            style={{ marginTop: 16 }}
          >
            <label>
              {t(
                'Apps Script — paste the full code into Extensions → Apps Script'
              )}
            </label>

            <textarea
              className="code-box tall"
              readOnly
              value={script}
            />

            <div style={{ marginTop: 8 }}>
              <button
                className="btn"
                onClick={() => copy(script)}
              >
                {t(
                  'Copy Full Apps Script'
                )}
              </button>
            </div>
          </div>
        )}
      </Modal>
    </>
  )
}
