'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, API_URL } from '../../../lib/api'
import Modal from '../../../components/Modal'

const emptyForm = {
  name: 'TikTok Ads',
  store_id: '',
  app_id: '',
  app_secret: ''
}

function statusLabel(value) {
  const map = {
    CONNECTED: 'Connected',
    CONFIGURED: 'Configured',
    DRAFT: 'Draft',
    DISCONNECTED: 'Disconnected'
  }

  return map[value] || value || 'Unknown'
}

function statusClass(value) {
  if (value === 'CONNECTED') return 'connected'
  if (value === 'CONFIGURED') return 'configured'
  if (value === 'DISCONNECTED') return 'disconnected'
  return 'draft'
}

export default function ConnectionsPage() {
  const [providers, setProviders] = useState([])
  const [connections, setConnections] = useState([])
  const [stores, setStores] = useState([])
  const [callbackUrl, setCallbackUrl] = useState('')

  const [providerOpen, setProviderOpen] = useState(false)
  const [formOpen, setFormOpen] = useState(false)
  const [accountsOpen, setAccountsOpen] = useState(false)

  const [editing, setEditing] = useState(null)
  const [accounts, setAccounts] = useState([])

  const [form, setForm] = useState(emptyForm)

  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  const [connectingId, setConnectingId] = useState(null)

  const tikTokProvider = useMemo(
    () => providers.find(p => p.provider === 'TIKTOK_ADS'),
    [providers]
  )

  const load = async () => {
    try {
      const [p, c, s, setup] = await Promise.all([
        api('/connections/providers'),
        api('/connections'),
        api('/stores'),
        api('/connections/tiktok/setup-info')
      ])

      setProviders(p || [])
      setConnections(c || [])
      setStores(s || [])
      setCallbackUrl(setup?.callback_url || '')
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    load()
  }, [])

  const flash = message => {
    setSuccess(message)

    setTimeout(() => {
      setSuccess('')
    }, 3500)
  }

  const copy = async text => {
    try {
      await navigator.clipboard.writeText(text)
      flash('Copied to clipboard.')
    } catch (_) {
      setError('Could not copy automatically.')
    }
  }

  const openCreateTikTok = () => {
    setEditing(null)

    setForm({
      ...emptyForm,
      store_id: stores[0]?.id || ''
    })

    setProviderOpen(false)
    setFormOpen(true)
  }

  const openEdit = row => {
    const config = row.config || {}

    setEditing(row)

    setForm({
      name: row.name || 'TikTok Ads',
      store_id: row.store_id || '',
      app_id: config.app_id || '',
      app_secret: ''
    })

    setFormOpen(true)
  }

  const save = async e => {
    e.preventDefault()

    setSaving(true)
    setError('')

    try {
      if (editing) {
        const body = {
          name: form.name,
          store_id: form.store_id || null,
          config: {
            app_id: form.app_id
          }
        }

        if (form.app_secret) {
          body.secrets = {
            app_secret: form.app_secret
          }
        }

        await api(
          `/connections/${editing.id}`,
          {
            method: 'PATCH',
            body
          }
        )

        flash('Connection updated.')
      } else {
        await api('/connections', {
          method: 'POST',
          body: {
            provider: 'TIKTOK_ADS',
            name: form.name,
            store_id: form.store_id || null,

            config: {
              app_id: form.app_id
            },

            secrets: {
              app_secret: form.app_secret
            }
          }
        })

        flash('TikTok connection created.')
      }

      setFormOpen(false)
      setEditing(null)
      setForm(emptyForm)

      await load()
    } catch (e2) {
      setError(e2.message)
    } finally {
      setSaving(false)
    }
  }

  const pollConnection = async (
    connectionId,
    popup
  ) => {
    const started = Date.now()

    while (Date.now() - started < 120000) {
      await new Promise(resolve =>
        setTimeout(resolve, 2000)
      )

      try {
        const row = await api(
          `/connections/${connectionId}`
        )

        if (row.status === 'CONNECTED') {
          try {
            popup?.close()
          } catch (_) {}

          flash('TikTok connected successfully.')
          setConnectingId(null)

          await load()

          return
        }

        if (
          row.last_test_status === 'FAILED'
        ) {
          try {
            popup?.close()
          } catch (_) {}

          setConnectingId(null)

          setError(
            row.last_test_message ||
            'TikTok connection failed.'
          )

          await load()

          return
        }
      } catch (_) {}
    }

    setConnectingId(null)

    setError(
      'Authorization is still pending. Refresh the page after completing TikTok authorization.'
    )
  }

  const connectTikTok = async row => {
    setError('')
    setConnectingId(row.id)

    const popup = window.open(
      'about:blank',
      'codops-tiktok-oauth',
      'width=720,height=760'
    )

    if (!popup) {
      setConnectingId(null)

      setError(
        'Popup blocked. Allow popups for CODOPS and try again.'
      )

      return
    }

    try {
      popup.document.write(
        '<p style="font-family:Arial;padding:30px">Preparing TikTok authorization...</p>'
      )

      const result = await api(
        `/connections/${row.id}/tiktok/authorize`,
        {
          method: 'POST'
        }
      )

      popup.location.href =
        result.authorization_url

      pollConnection(
        row.id,
        popup
      )
    } catch (e) {
      try {
        popup.close()
      } catch (_) {}

      setConnectingId(null)
      setError(e.message)
    }
  }

  const importAccounts = async row => {
    setError('')
    setConnectingId(row.id)

    try {
      const result = await api(
        `/connections/${row.id}/tiktok/import-accounts`,
        {
          method: 'POST'
        }
      )

      flash(
        `${result.imported || 0} TikTok ad account(s) imported.`
      )

      await load()

      const imported = await api(
        `/connections/${row.id}/tiktok/imported-accounts`
      )

      setAccounts(imported || [])
      setAccountsOpen(true)

    } catch (e) {
      setError(e.message)

    } finally {
      setConnectingId(null)
    }
  }

  const viewAccounts = async row => {
    setError('')

    try {
      const result = await api(
        `/connections/${row.id}/tiktok/imported-accounts`
      )

      setAccounts(result || [])

      setAccountsOpen(true)
    } catch (e) {
      setError(e.message)
    }
  }

  const disconnect = async row => {
    if (
      !window.confirm(
        `Disconnect ${row.name}?`
      )
    ) {
      return
    }

    try {
      await api(
        `/connections/${row.id}/disconnect`,
        {
          method: 'POST'
        }
      )

      flash('Connection disconnected.')
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const enable = async row => {
    try {
      await api(
        `/connections/${row.id}/enable`,
        {
          method: 'POST'
        }
      )

      flash('Connection enabled.')
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div className="connections-page">
      <div className="connections-hero">
        <div>
          <span>COD OPS · CONNECTIONS</span>

          <h1>Connections</h1>

          <p>
            Connect advertising and funding providers
            without changing Railway or environment files.
          </p>
        </div>

        <button
          className="btn connections-add"
          onClick={() =>
            setProviderOpen(true)
          }
        >
          + Add Connection
        </button>
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

      <div className="connections-overview">
        <div>
          <span>Total Connections</span>
          <strong>
            {connections.length}
          </strong>
        </div>

        <div>
          <span>Connected</span>
          <strong>
            {
              connections.filter(
                x => x.status === 'CONNECTED'
              ).length
            }
          </strong>
        </div>

        <div>
          <span>Configured</span>
          <strong>
            {
              connections.filter(
                x => x.status === 'CONFIGURED'
              ).length
            }
          </strong>
        </div>

        <div>
          <span>Needs Setup</span>
          <strong>
            {
              connections.filter(
                x =>
                  x.status === 'DRAFT' ||
                  x.status === 'DISCONNECTED'
              ).length
            }
          </strong>
        </div>
      </div>

      <div className="panel connections-panel">
        <div className="panel-head">
          <div>
            <h2>Connected Providers</h2>

            <p>
              Credentials are encrypted and never
              displayed again after saving.
            </p>
          </div>
        </div>

        <div className="connections-grid">
          {connections.map(row => {
            const store =
              stores.find(
                s => s.id === row.store_id
              )

            return (
              <div
                className="connection-card"
                key={row.id}
              >
                <div className="connection-card-top">
                  <div className="provider-logo tiktok">
                    TT
                  </div>

                  <div>
                    <strong>
                      {row.name}
                    </strong>

                    <small>
                      {row.provider_label}
                    </small>
                  </div>

                  <span
                    className={
                      `connection-status ${
                        statusClass(row.status)
                      }`
                    }
                  >
                    {statusLabel(row.status)}
                  </span>
                </div>

                <div className="connection-meta">
                  <div>
                    <span>Store</span>
                    <strong>
                      {store?.name || 'Global'}
                    </strong>
                  </div>

                  <div>
                    <span>App ID</span>
                    <strong>
                      {row.config?.app_id || '—'}
                    </strong>
                  </div>

                  <div>
                    <span>Credentials</span>
                    <strong>
                      {row.has_credentials
                        ? 'Saved securely'
                        : 'Missing'}
                    </strong>
                  </div>

                  <div>
                    <span>Last Test</span>
                    <strong>
                      {row.last_test_status || 'Not tested'}
                    </strong>
                  </div>
                </div>

                {row.last_test_message && (
                  <div className="connection-message">
                    {row.last_test_message}
                  </div>
                )}

                <div className="connection-actions">
                  <button
                    className="btn small secondary"
                    onClick={() =>
                      openEdit(row)
                    }
                  >
                    Configure
                  </button>

                  {row.is_active ? (
                    <button
                      className="btn small"
                      disabled={
                        connectingId === row.id
                      }
                      onClick={() =>
                        connectTikTok(row)
                      }
                    >
                      {connectingId === row.id
                        ? 'Connecting...'
                        : row.status === 'CONNECTED'
                          ? 'Reconnect TikTok'
                          : 'Connect TikTok'}
                    </button>
                  ) : (
                    <button
                      className="btn small"
                      onClick={() =>
                        enable(row)
                      }
                    >
                      Enable
                    </button>
                  )}

                  {row.status === 'CONNECTED' && (
                    <>
                      <button
                        className="btn small"
                        disabled={
                          connectingId === row.id
                        }
                        onClick={() =>
                          importAccounts(row)
                        }
                      >
                        {connectingId === row.id
                          ? 'Syncing...'
                          : 'Import / Sync Accounts'}
                      </button>

                      <button
                        className="btn small secondary"
                        onClick={() =>
                          viewAccounts(row)
                        }
                      >
                        View Accounts
                      </button>
                    </>
                  )}

                  {row.is_active && (
                    <button
                      className="btn small danger"
                      onClick={() =>
                        disconnect(row)
                      }
                    >
                      Disconnect
                    </button>
                  )}
                </div>
              </div>
            )
          })}

          {!connections.length && (
            <div className="connections-empty">
              <strong>
                No connections yet
              </strong>

              <p>
                Add TikTok Ads to start importing
                ad accounts into CODOPS.
              </p>

              <button
                className="btn"
                onClick={() =>
                  setProviderOpen(true)
                }
              >
                + Add Connection
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="panel connections-panel">
        <div className="panel-head">
          <div>
            <h2>Setup Information</h2>

            <p>
              Register this callback once inside
              your TikTok developer application.
            </p>
          </div>
        </div>

        <div className="callback-box">
          <div>
            <span>
              TikTok Callback URL
            </span>

            <code>
              {callbackUrl || 'Loading...'}
            </code>
          </div>

          <button
            className="btn small secondary"
            onClick={() =>
              callbackUrl && copy(callbackUrl)
            }
          >
            Copy
          </button>
        </div>
      </div>

      <Modal
        open={providerOpen}
        title="Add Connection"
        onClose={() =>
          setProviderOpen(false)
        }
        wide
      >
        <div className="provider-picker">
          <button
            className="provider-option enabled"
            onClick={openCreateTikTok}
          >
            <div className="provider-logo tiktok">
              TT
            </div>

            <strong>TikTok Ads</strong>

            <span>
              Connect advertiser accounts,
              balance and spend.
            </span>

            <small>Available now</small>
          </button>

          {providers
            .filter(
              p => p.provider !== 'TIKTOK_ADS'
            )
            .map(provider => (
              <div
                className="provider-option disabled"
                key={provider.provider}
              >
                <div className="provider-logo">
                  {provider.label
                    .slice(0, 2)
                    .toUpperCase()}
                </div>

                <strong>
                  {provider.label}
                </strong>

                <span>
                  {provider.category}
                </span>

                <small>
                  {provider.status}
                </small>
              </div>
            ))}
        </div>
      </Modal>

      <Modal
        open={formOpen}
        title={
          editing
            ? 'Configure TikTok'
            : 'Add TikTok Ads'
        }
        onClose={() => {
          if (!saving) {
            setFormOpen(false)
            setEditing(null)
          }
        }}
      >
        <form onSubmit={save}>
          <div className="connection-step-note">
            <strong>
              TikTok Developer App
            </strong>

            <span>
              Create/approve the developer app once,
              then future advertiser connections can
              be managed from CODOPS.
            </span>
          </div>

          <div className="field">
            <label>
              Connection Name
            </label>

            <input
              required
              value={form.name}
              onChange={e =>
                setForm({
                  ...form,
                  name: e.target.value
                })
              }
              placeholder="TikTok Morocco"
            />
          </div>

          <div className="field">
            <label>
              Store
            </label>

            <select
              value={form.store_id}
              onChange={e =>
                setForm({
                  ...form,
                  store_id: e.target.value
                })
              }
            >
              <option value="">
                Global / No Store
              </option>

              {stores.map(store => (
                <option
                  key={store.id}
                  value={store.id}
                >
                  {store.name}
                </option>
              ))}
            </select>
          </div>

          <div className="field">
            <label>
              TikTok App ID
            </label>

            <input
              required
              value={form.app_id}
              onChange={e =>
                setForm({
                  ...form,
                  app_id: e.target.value
                })
              }
              placeholder="App ID"
            />
          </div>

          <div className="field">
            <label>
              TikTok App Secret
            </label>

            <input
              required={!editing}
              type="password"
              autoComplete="new-password"
              value={form.app_secret}
              onChange={e =>
                setForm({
                  ...form,
                  app_secret: e.target.value
                })
              }
              placeholder={
                editing
                  ? 'Leave blank to keep current secret'
                  : 'App Secret'
              }
            />

            <small>
              Stored encrypted. CODOPS will never
              display the saved secret again.
            </small>
          </div>

          <div className="callback-mini">
            <span>
              Callback URL
            </span>

            <code>
              {callbackUrl || 'Loading...'}
            </code>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              disabled={saving}
              onClick={() => {
                setFormOpen(false)
                setEditing(null)
              }}
            >
              Cancel
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? 'Saving...'
                : 'Save Connection'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        open={accountsOpen}
        title="Authorized TikTok Accounts"
        onClose={() =>
          setAccountsOpen(false)
        }
      >
        <div className="authorized-accounts">
          {accounts.map(account => (
            <div
              className="authorized-account-row"
              key={
                account.id ||
                account.advertiser_id
              }
            >
              <div>
                <span>
                  {account.name || 'TikTok Ad Account'}
                </span>

                <strong>
                  {account.advertiser_id}
                </strong>

                <small>
                  {account.balance || 0}
                  {' '}
                  {account.currency || ''}
                  {' · '}
                  {account.status || 'UNKNOWN'}
                </small>
              </div>

              <span className="connection-status connected">
                Imported
              </span>
            </div>
          ))}

          {!accounts.length && (
            <div className="empty">
              No authorized ad accounts returned.
            </div>
          )}
        </div>
      </Modal>
    </div>
  )
}
