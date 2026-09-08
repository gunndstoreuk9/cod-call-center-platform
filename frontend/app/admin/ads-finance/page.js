'use client'

import { useEffect, useMemo, useState } from 'react'
import { api } from '../../../lib/api'
import Modal from '../../../components/Modal'

const emptyRule = {
  threshold_balance: '10',
  refill_amount: '20',
  daily_cap: '100',
  monthly_cap: '2000',
  cooldown_minutes: '30'
}

export default function AdsFinancePage() {
  const [data, setData] = useState({
    accounts_count: 0,
    active_accounts: 0,
    low_balance_accounts: 0,
    mapped_accounts: 0,
    currency_totals: [],
    accounts: []
  })

  const [stores, setStores] = useState([])
  const [products, setProducts] = useState([])
  const [transactions, setTransactions] = useState([])

  const [storeId, setStoreId] = useState('')
  const [productId, setProductId] = useState('')

  const [ruleAccount, setRuleAccount] = useState(null)
  const [ruleForm, setRuleForm] = useState(emptyRule)

  const [demoAccount, setDemoAccount] = useState(null)
  const [demoBalance, setDemoBalance] = useState('25')
  const [demoSpend, setDemoSpend] = useState('8')

  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)

  const query = () => {
    const p = new URLSearchParams()

    if (storeId) p.set('store_id', storeId)
    if (productId) p.set('product_id', productId)

    const text = p.toString()

    return text ? `?${text}` : ''
  }

  const load = async () => {
    try {
      const [dashboard, s, p, tx] = await Promise.all([
        api(`/ads-finance/dashboard${query()}`),
        api('/stores'),
        api('/products'),
        api('/ads-finance/transactions?limit=20')
      ])

      setData(dashboard || {})
      setStores(s || [])
      setProducts(p || [])
      setTransactions(tx || [])
      setError('')
    } catch (e) {
      setError(e.message)
    }
  }

  useEffect(() => {
    load()
  }, [storeId, productId])

  const flash = message => {
    setSuccess(message)

    setTimeout(() => {
      setSuccess('')
    }, 3500)
  }

  const selectedCurrency =
    data.currency_totals?.length === 1
      ? data.currency_totals[0]
      : null

  const productsForAccount = account => {
    if (!account?.store?.id) {
      return products
    }

    return products.filter(
      p => p.store_id === account.store.id
    )
  }

  const mapProduct = async (account, nextProductId) => {
    setError('')

    try {
      await api(
        `/ads-finance/accounts/${account.id}/product`,
        {
          method: 'PUT',
          body: {
            product_id: nextProductId || null
          }
        }
      )

      flash('Product mapping updated.')
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const openRule = account => {
    const rule = account.rule

    setRuleAccount(account)

    setRuleForm({
      threshold_balance:
        rule?.threshold_balance ?? '10',

      refill_amount:
        rule?.refill_amount ?? '20',

      daily_cap:
        rule?.daily_cap ?? '100',

      monthly_cap:
        rule?.monthly_cap ?? '2000',

      cooldown_minutes:
        String(rule?.cooldown_minutes ?? 30)
    })
  }

  const saveRule = async e => {
    e.preventDefault()

    if (!ruleAccount) return

    setSaving(true)
    setError('')

    try {
      await api(
        `/ads-finance/accounts/${ruleAccount.id}/rule`,
        {
          method: 'PUT',

          body: {
            threshold_balance:
              Number(ruleForm.threshold_balance || 0),

            refill_amount:
              Number(ruleForm.refill_amount || 0),

            daily_cap:
              ruleForm.daily_cap === ''
                ? null
                : Number(ruleForm.daily_cap),

            monthly_cap:
              ruleForm.monthly_cap === ''
                ? null
                : Number(ruleForm.monthly_cap),

            cooldown_minutes:
              Number(ruleForm.cooldown_minutes || 30)
          }
        }
      )

      setRuleAccount(null)
      flash('Funding rule saved.')
      await load()
    } catch (e2) {
      setError(e2.message)
    } finally {
      setSaving(false)
    }
  }

  const openDemo = account => {
    setDemoAccount(account)
    setDemoBalance(account.balance || '25')
    setDemoSpend(account.spend_today || '8')
  }

  const saveDemo = async e => {
    e.preventDefault()

    if (!demoAccount) return

    setSaving(true)
    setError('')

    try {
      await api(
        `/ads-finance/accounts/${demoAccount.id}/demo-metrics`,
        {
          method: 'POST',
          body: {
            balance: Number(demoBalance || 0),
            spend_today: Number(demoSpend || 0)
          }
        }
      )

      setDemoAccount(null)
      flash('Demo metrics updated.')
      await load()
    } catch (e2) {
      setError(e2.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="ads-finance-page">
      <div className="af-hero">
        <div>
          <span>COD OPS · ADS FINANCE</span>
          <h1>Ads Finance</h1>

          <p>
            Monitor ad account balances, spend,
            product mapping and funding rules.
          </p>
        </div>

        <div className="af-safe">
          <strong>SAFE MODE</strong>
          <span>Automatic funding is locked OFF</span>
        </div>
      </div>

      {error && (
        <div className="error">{error}</div>
      )}

      {success && (
        <div className="success-box">
          {success}
        </div>
      )}

      <div className="af-filters">
        <select
          value={storeId}
          onChange={e => {
            setStoreId(e.target.value)
            setProductId('')
          }}
        >
          <option value="">All Stores</option>

          {stores.map(store => (
            <option
              key={store.id}
              value={store.id}
            >
              {store.name}
            </option>
          ))}
        </select>

        <select
          value={productId}
          onChange={e =>
            setProductId(e.target.value)
          }
        >
          <option value="">All Products</option>

          {products
            .filter(
              p =>
                !storeId ||
                p.store_id === storeId
            )
            .map(product => (
              <option
                key={product.id}
                value={product.id}
              >
                {product.name}
              </option>
            ))}
        </select>

        <button
          className="btn secondary"
          onClick={load}
        >
          Refresh
        </button>
      </div>

      <div className="af-kpis">
        <div>
          <span>Total Balance</span>
          <strong>
            {selectedCurrency
              ? `${Number(selectedCurrency.balance).toLocaleString()} ${selectedCurrency.currency}`
              : data.currency_totals?.length
                ? 'Multiple'
                : '0'}
          </strong>
        </div>

        <div>
          <span>Spend Today</span>
          <strong>
            {selectedCurrency
              ? `${Number(selectedCurrency.spend_today).toLocaleString()} ${selectedCurrency.currency}`
              : data.currency_totals?.length
                ? 'Multiple'
                : '0'}
          </strong>
        </div>

        <div>
          <span>Active Accounts</span>
          <strong>
            {data.active_accounts || 0}
          </strong>
        </div>

        <div className={
          data.low_balance_accounts
            ? 'warning'
            : ''
        }>
          <span>Low Balance</span>
          <strong>
            {data.low_balance_accounts || 0}
          </strong>
        </div>

        <div>
          <span>Mapped Products</span>
          <strong>
            {data.mapped_accounts || 0}
            /{data.accounts_count || 0}
          </strong>
        </div>
      </div>

      <div className="panel af-panel">
        <div className="panel-head">
          <div>
            <h2>Ad Accounts</h2>
            <p>
              Balance, spend, product mapping and funding rules.
            </p>
          </div>
        </div>

        <div className="af-table-wrap">
          <table className="af-table">
            <thead>
              <tr>
                <th>Account</th>
                <th>Balance</th>
                <th>Spend Today</th>
                <th>Product</th>
                <th>Funding Rule</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {(data.accounts || []).map(account => (
                <tr key={account.id}>
                  <td>
                    <div className="af-account-name">
                      <strong>
                        {account.name}
                      </strong>

                      <small>
                        {account.advertiser_id}
                      </small>

                      {account.demo && (
                        <span className="af-demo-badge">
                          DEMO
                        </span>
                      )}
                    </div>
                  </td>

                  <td>
                    <strong>
                      {Number(
                        account.balance || 0
                      ).toLocaleString()}
                      {' '}
                      {account.currency}
                    </strong>

                    {account.low_balance && (
                      <small className="af-low">
                        Low balance
                      </small>
                    )}
                  </td>

                  <td>
                    {Number(
                      account.spend_today || 0
                    ).toLocaleString()}
                    {' '}
                    {account.currency}
                  </td>

                  <td>
                    <select
                      value={
                        account.product?.id || ''
                      }
                      onChange={e =>
                        mapProduct(
                          account,
                          e.target.value
                        )
                      }
                    >
                      <option value="">
                        Not mapped
                      </option>

                      {productsForAccount(account)
                        .map(product => (
                          <option
                            value={product.id}
                            key={product.id}
                          >
                            {product.name}
                          </option>
                        ))}
                    </select>
                  </td>

                  <td>
                    {account.rule ? (
                      <div className="af-rule-summary">
                        <strong>
                          ≤ {account.rule.threshold_balance}
                          {' '}
                          {account.currency}
                        </strong>

                        <small>
                          Refill {account.rule.refill_amount}
                          {' '}
                          {account.currency}
                        </small>

                        <span>
                          AUTO OFF
                        </span>
                      </div>
                    ) : (
                      <span className="muted">
                        No rule
                      </span>
                    )}
                  </td>

                  <td>
                    <span
                      className={
                        account.low_balance
                          ? 'af-status low'
                          : account.status === 'ACTIVE'
                            ? 'af-status active'
                            : 'af-status'
                      }
                    >
                      {account.low_balance
                        ? 'LOW BALANCE'
                        : account.status}
                    </span>
                  </td>

                  <td>
                    <div className="af-actions">
                      <button
                        className="btn small secondary"
                        onClick={() =>
                          openRule(account)
                        }
                      >
                        Rule
                      </button>

                      {account.demo && (
                        <button
                          className="btn small"
                          onClick={() =>
                            openDemo(account)
                          }
                        >
                          Simulate
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}

              {!data.accounts?.length && (
                <tr>
                  <td colSpan="7">
                    <div className="af-empty">
                      No ad accounts found.
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel af-panel">
        <div className="panel-head">
          <div>
            <h2>Funding Transactions</h2>
            <p>
              Transaction history will appear here
              when manual funding is enabled.
            </p>
          </div>
        </div>

        <div className="af-table-wrap">
          <table className="af-table">
            <thead>
              <tr>
                <th>Date</th>
                <th>Provider</th>
                <th>Type</th>
                <th>Amount</th>
                <th>Status</th>
              </tr>
            </thead>

            <tbody>
              {transactions.map(tx => (
                <tr key={tx.id}>
                  <td>
                    {tx.created_at
                      ? new Date(
                          tx.created_at
                        ).toLocaleString()
                      : '—'}
                  </td>

                  <td>{tx.provider}</td>
                  <td>{tx.transaction_type}</td>

                  <td>
                    {tx.amount} {tx.currency}
                  </td>

                  <td>{tx.status}</td>
                </tr>
              ))}

              {!transactions.length && (
                <tr>
                  <td colSpan="5">
                    <div className="af-empty">
                      No funding transactions yet.
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        open={!!ruleAccount}
        title="Funding Rule"
        onClose={() => {
          if (!saving) setRuleAccount(null)
        }}
      >
        <form onSubmit={saveRule}>
          <div className="af-lock-box">
            <strong>Automatic Top-Up Locked</strong>
            <span>
              This phase saves the rule only.
              No real money can move.
            </span>
          </div>

          <div className="field">
            <label>Low Balance Threshold</label>
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={ruleForm.threshold_balance}
              onChange={e =>
                setRuleForm({
                  ...ruleForm,
                  threshold_balance: e.target.value
                })
              }
            />
          </div>

          <div className="field">
            <label>Refill Amount</label>
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={ruleForm.refill_amount}
              onChange={e =>
                setRuleForm({
                  ...ruleForm,
                  refill_amount: e.target.value
                })
              }
            />
          </div>

          <div className="field-grid">
            <div className="field">
              <label>Daily Cap</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={ruleForm.daily_cap}
                onChange={e =>
                  setRuleForm({
                    ...ruleForm,
                    daily_cap: e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>Monthly Cap</label>
              <input
                type="number"
                min="0"
                step="0.01"
                value={ruleForm.monthly_cap}
                onChange={e =>
                  setRuleForm({
                    ...ruleForm,
                    monthly_cap: e.target.value
                  })
                }
              />
            </div>
          </div>

          <div className="field">
            <label>Cooldown Minutes</label>
            <input
              type="number"
              min="5"
              max="1440"
              required
              value={ruleForm.cooldown_minutes}
              onChange={e =>
                setRuleForm({
                  ...ruleForm,
                  cooldown_minutes: e.target.value
                })
              }
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() =>
                setRuleAccount(null)
              }
            >
              Cancel
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? 'Saving...'
                : 'Save Rule'}
            </button>
          </div>
        </form>
      </Modal>

      <Modal
        open={!!demoAccount}
        title="Demo Balance Simulator"
        onClose={() => {
          if (!saving) setDemoAccount(null)
        }}
      >
        <form onSubmit={saveDemo}>
          <div className="af-lock-box safe">
            <strong>Demo Only</strong>
            <span>
              Change these values to test
              low-balance logic safely.
            </span>
          </div>

          <div className="field">
            <label>Account Balance</label>
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={demoBalance}
              onChange={e =>
                setDemoBalance(e.target.value)
              }
            />
          </div>

          <div className="field">
            <label>Spend Today</label>
            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={demoSpend}
              onChange={e =>
                setDemoSpend(e.target.value)
              }
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() =>
                setDemoAccount(null)
              }
            >
              Cancel
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              Apply Demo Values
            </button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
