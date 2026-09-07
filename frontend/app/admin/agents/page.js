'use client'

import { useEffect, useState } from 'react'
import { api, money } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import Modal from '../../../components/Modal'
import StatusBadge from '../../../components/StatusBadge'

const empty = {
  username: '',
  password: '',
  display_name: '',
  phone: '',
  email: '',
  commission_default: '5',
  product_ids: []
}

export default function AgentsPage() {
  const { t } = useI18n()

  const [agents, setAgents] = useState([])
  const [products, setProducts] = useState([])

  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(empty)

  const [accessOpen, setAccessOpen] = useState(false)
  const [selectedAgent, setSelectedAgent] = useState(null)
  const [accessProducts, setAccessProducts] = useState([])

  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)

  const load = () =>
    Promise.all([
      api('/agents'),
      api('/products?status=ACTIVE')
    ])
      .then(([a, p]) => {
        setAgents(a)
        setProducts(p)
      })
      .catch(e => setError(e.message))

  useEffect(() => {
    load()
  }, [])

  const toggleProduct = id =>
    setForm(f => ({
      ...f,
      product_ids: f.product_ids.includes(id)
        ? f.product_ids.filter(x => x !== id)
        : [...f.product_ids, id]
    }))

  const submit = async e => {
    e.preventDefault()
    setSaving(true)
    setError('')

    try {
      await api('/agents', {
        method: 'POST',
        body: {
          ...form,
          commission_default: Number(form.commission_default),
          role: 'AGENT'
        }
      })

      setOpen(false)
      setForm(empty)
      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const toggle = async a => {
    try {
      await api(`/agents/${a.id}`, {
        method: 'PATCH',
        body: {
          is_active: !a.is_active
        }
      })

      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const openAccess = agent => {
    setSelectedAgent(agent)
    setAccessProducts(agent.product_ids || [])
    setError('')
    setAccessOpen(true)
  }

  const toggleAccessProduct = id => {
    setAccessProducts(current =>
      current.includes(id)
        ? current.filter(x => x !== id)
        : [...current, id]
    )
  }

  const selectAllProducts = () => {
    setAccessProducts(products.map(p => p.id))
  }

  const clearAllProducts = () => {
    setAccessProducts([])
  }

  const saveAccess = async () => {
    if (!selectedAgent) return

    setSaving(true)
    setError('')

    try {
      await api(`/agents/${selectedAgent.id}`, {
        method: 'PATCH',
        body: {
          product_ids: accessProducts
        }
      })

      setAccessOpen(false)
      setSelectedAgent(null)
      setAccessProducts([])
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
          <h1>{t('Agents')}</h1>
          <p>
            {t('Create agents, assign products, control commission and access.')}
          </p>
        </div>

        <button
          className="btn"
          onClick={() => setOpen(true)}
        >
          {t('+ Add Agent')}
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      <div className="panel">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Agent')}</th>
                <th>{t('Username')}</th>
                <th>{t('Products')}</th>
                <th>{t('Default Commission')}</th>
                <th>{t('Unpaid Balance')}</th>
                <th>{t('Status')}</th>
                <th>{t('Action')}</th>
              </tr>
            </thead>

            <tbody>
              {agents.map(a => (
                <tr key={a.id}>
                  <td>
                    <strong>{a.display_name}</strong>
                  </td>

                  <td>@{a.username}</td>

                  <td>
                    <strong>{a.product_ids?.length || 0}</strong>
                    <br />
                    <small>allowed products</small>
                  </td>

                  <td>{money(a.commission_default)}</td>

                  <td>
                    <strong>{money(a.current_balance)}</strong>
                  </td>

                  <td>
                    <StatusBadge
                      value={a.is_active ? 'ACTIVE' : 'INACTIVE'}
                    />
                  </td>

                  <td>
                    <div
                      style={{
                        display: 'flex',
                        gap: 8,
                        flexWrap: 'wrap'
                      }}
                    >
                      <button
                        className="btn small"
                        onClick={() => openAccess(a)}
                      >
                        Manage Access
                      </button>

                      <button
                        className="btn small secondary"
                        onClick={() => toggle(a)}
                      >
                        {a.is_active ? t('Disable') : t('Enable')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* ADD AGENT */}
      <Modal
        open={open}
        title="Add Agent"
        onClose={() => setOpen(false)}
        wide
      >
        <form onSubmit={submit}>
          <div className="form-grid">

            <div className="field">
              <label>{t('Display Name')}</label>
              <input
                required
                value={form.display_name}
                onChange={e =>
                  setForm({
                    ...form,
                    display_name: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Username')}</label>
              <input
                required
                value={form.username}
                onChange={e =>
                  setForm({
                    ...form,
                    username: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Password')}</label>
              <input
                type="password"
                minLength="8"
                required
                value={form.password}
                onChange={e =>
                  setForm({
                    ...form,
                    password: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Default Commission')}</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={form.commission_default}
                onChange={e =>
                  setForm({
                    ...form,
                    commission_default: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Phone')}</label>
              <input
                value={form.phone}
                onChange={e =>
                  setForm({
                    ...form,
                    phone: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>Email</label>
              <input
                type="email"
                value={form.email}
                onChange={e =>
                  setForm({
                    ...form,
                    email: e.target.value
                  })
                }
              />
            </div>

            <div className="field full">
              <label>{t('Allowed Products')}</label>

              <div className="check-grid">
                {products.map(p => (
                  <label
                    className="check"
                    key={p.id}
                  >
                    <input
                      type="checkbox"
                      checked={form.product_ids.includes(p.id)}
                      onChange={() => toggleProduct(p.id)}
                    />

                    <span>
                      {p.name}
                      <br />
                      <small>{p.sku}</small>
                    </span>
                  </label>
                ))}
              </div>
            </div>

          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() => setOpen(false)}
            >
              {t('Cancel')}
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving ? t('Creating...') : t('Create Agent')}
            </button>
          </div>
        </form>
      </Modal>

      {/* MANAGE PRODUCT ACCESS */}
      <Modal
        open={accessOpen}
        title={
          selectedAgent
            ? `Product Access — ${selectedAgent.display_name}`
            : 'Product Access'
        }
        onClose={() => setAccessOpen(false)}
        wide
      >
        <div style={{ marginBottom: 18 }}>
          <p style={{ marginTop: 0 }}>
            Choose which products this agent is allowed to work with.
          </p>

          <div
            style={{
              display: 'flex',
              gap: 8,
              marginBottom: 18
            }}
          >
            <button
              type="button"
              className="btn small secondary"
              onClick={selectAllProducts}
            >
              Select All
            </button>

            <button
              type="button"
              className="btn small secondary"
              onClick={clearAllProducts}
            >
              Clear All
            </button>
          </div>

          <div className="check-grid">
            {products.map(p => (
              <label
                className="check"
                key={p.id}
              >
                <input
                  type="checkbox"
                  checked={accessProducts.includes(p.id)}
                  onChange={() => toggleAccessProduct(p.id)}
                />

                <span>
                  <strong>{p.name}</strong>
                  <br />
                  <small>{p.sku}</small>
                </span>
              </label>
            ))}
          </div>
        </div>

        <div className="form-actions">
          <button
            type="button"
            className="btn secondary"
            onClick={() => setAccessOpen(false)}
          >
            Cancel
          </button>

          <button
            type="button"
            className="btn"
            disabled={saving}
            onClick={saveAccess}
          >
            {saving ? 'Saving...' : 'Save Access'}
          </button>
        </div>
      </Modal>
    </>
  )
}
