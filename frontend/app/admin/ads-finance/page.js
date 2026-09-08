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
  const [fundingAccounts, setFundingAccounts] = useState([])

  const [walletAccount, setWalletAccount] = useState(null)
  const [walletName, setWalletName] = useState('Demo Funding Wallet')
  const [walletStartingBalance, setWalletStartingBalance] = useState('1000')

  const [fundingSimulator, setFundingSimulator] = useState(null)
  const [fundingSimBalance, setFundingSimBalance] = useState('1000')

  const [storeId, setStoreId] = useState('')
  const [productId, setProductId] = useState('')

  const [ruleAccount, setRuleAccount] = useState(null)
  const [ruleForm, setRuleForm] = useState(emptyRule)

  const [demoAccount, setDemoAccount] = useState(null)
  const [demoBalance, setDemoBalance] = useState('25')
  const [demoSpend, setDemoSpend] = useState('8')

  const [topupAccount, setTopupAccount] = useState(null)
  const [topupAmount, setTopupAmount] = useState('20')

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
      const [dashboard, s, p, tx, funding] = await Promise.all([
        api(`/ads-finance/dashboard${query()}`),
        api('/stores'),
        api('/products'),
        api('/ads-finance/transactions?limit=20'),
        api('/ads-finance/funding-accounts')
      ])

      setData(dashboard || {})
      setStores(s || [])
      setProducts(p || [])
      setTransactions(tx || [])
      setFundingAccounts(funding || [])
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

  const fundingCurrencyTotals = useMemo(() => {
    const totals = {}

    fundingAccounts
      .filter(x => x.is_active)
      .forEach(account => {
        const currency = account.currency || 'USD'

        totals[currency] =
          (totals[currency] || 0) +
          Number(account.balance || 0)
      })

    return Object.entries(totals).map(
      ([currency, balance]) => ({
        currency,
        balance
      })
    )
  }, [fundingAccounts])

  const selectedFundingCurrency =
    fundingCurrencyTotals.length === 1
      ? fundingCurrencyTotals[0]
      : null

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

  const openCreateWallet = account => {
    setWalletAccount(account)
    setWalletName('Demo Funding Wallet')
    setWalletStartingBalance('1000')
  }

  const createDemoWallet = async e => {
    e.preventDefault()

    if (!walletAccount) return

    setSaving(true)
    setError('')

    try {
      const result = await api(
        `/ads-finance/accounts/${walletAccount.id}/demo-funding-wallet`,
        {
          method: 'POST',
          body: {
            name: walletName,
            starting_balance:
              Number(walletStartingBalance || 0)
          }
        }
      )

      const funding =
        result.funding_account

      if (funding?.id) {
        await api(
          `/ads-finance/accounts/${walletAccount.id}/funding-source`,
          {
            method: 'PUT',
            body: {
              funding_account_id:
                funding.id
            }
          }
        )
      }

      setWalletAccount(null)

      flash(
        result.created
          ? 'Demo funding wallet created and connected.'
          : 'Existing demo funding wallet connected.'
      )

      await load()

    } catch (e2) {
      setError(e2.message)

    } finally {
      setSaving(false)
    }
  }

  const setFundingSource = async (
    account,
    fundingAccountId
  ) => {
    setError('')

    try {
      await api(
        `/ads-finance/accounts/${account.id}/funding-source`,
        {
          method: 'PUT',
          body: {
            funding_account_id:
              fundingAccountId || null
          }
        }
      )

      flash('Funding source updated.')
      await load()

    } catch (e) {
      setError(e.message)
    }
  }

  const openFundingSimulator = funding => {
    setFundingSimulator(funding)
    setFundingSimBalance(
      funding.balance || '1000'
    )
  }

  const saveFundingSimulator = async e => {
    e.preventDefault()

    if (!fundingSimulator) return

    setSaving(true)
    setError('')

    try {
      await api(
        `/ads-finance/funding-accounts/${fundingSimulator.id}/demo-balance`,
        {
          method: 'POST',
          body: {
            balance:
              Number(fundingSimBalance || 0)
          }
        }
      )

      setFundingSimulator(null)
      flash('Demo funding wallet balance updated.')

      await load()

    } catch (e2) {
      setError(e2.message)

    } finally {
      setSaving(false)
    }
  }

  const fundingOptionsForAccount = account =>
    fundingAccounts.filter(
      funding =>
        funding.is_active &&
        funding.currency === account.currency &&
        (
          !funding.integration_id ||
          !account.connection?.id ||
          funding.integration_id ===
            account.connection.id
        )
    )

  const openDemoTopup = account => {
    setTopupAccount(account)

    setTopupAmount(
      account.rule?.refill_amount || '20'
    )
  }

  const saveDemoTopup = async e => {
    e.preventDefault()

    if (!topupAccount) return

    setSaving(true)
    setError('')

    try {
      const result = await api(
        `/ads-finance/accounts/${topupAccount.id}/demo-topup`,
        {
          method: 'POST',

          body: {
            amount:
              Number(topupAmount || 0)
          }
        }
      )

      setTopupAccount(null)

      flash(
        `Demo top-up completed: +${result.transaction?.amount || topupAmount} ${result.transaction?.currency || topupAccount.currency}.`
      )

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
          <span>Funding Available</span>
          <strong>
            {selectedFundingCurrency
              ? `${Number(
                  selectedFundingCurrency.balance
                ).toLocaleString()} ${selectedFundingCurrency.currency}`
              : fundingCurrencyTotals.length
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
                <th>Funding Source</th>
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
                    <div className="af-funding-source">
                      <select
                        value={
                          account.funding_source?.id || ''
                        }
                        onChange={e =>
                          setFundingSource(
                            account,
                            e.target.value
                          )
                        }
                      >
                        <option value="">
                          No funding source
                        </option>

                        {fundingOptionsForAccount(account)
                          .map(funding => (
                            <option
                              key={funding.id}
                              value={funding.id}
                            >
                              {funding.name}
                              {' · '}
                              {Number(
                                funding.balance || 0
                              ).toLocaleString()}
                              {' '}
                              {funding.currency}
                            </option>
                          ))}
                      </select>

                      {account.demo &&
                        !fundingOptionsForAccount(account).length && (
                          <button
                            className="btn small secondary"
                            onClick={() =>
                              openCreateWallet(account)
                            }
                          >
                            + Create Demo Wallet
                          </button>
                        )}

                      {account.funding_source && (
                        <small>
                          Available:
                          {' '}
                          {Number(
                            account.funding_source.balance || 0
                          ).toLocaleString()}
                          {' '}
                          {account.funding_source.currency}
                        </small>
                      )}
                    </div>
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
                        <>
                          <button
                            className="btn small"
                            disabled={
                              !account.funding_source
                            }
                            title={
                              account.funding_source
                                ? 'Demo top up'
                                : 'Select a funding source first'
                            }
                            onClick={() =>
                              openDemoTopup(account)
                            }
                          >
                            Demo Top Up
                          </button>

                          <button
                            className="btn small secondary"
                            onClick={() =>
                              openDemo(account)
                            }
                          >
                            Simulate
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}

              {!data.accounts?.length && (
                <tr>
                  <td colSpan="8">
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
            <h2>Funding Sources</h2>

            <p>
              Funding wallets available for ad-account
              top-ups.
            </p>
          </div>
        </div>

        <div className="af-table-wrap">
          <table className="af-table">
            <thead>
              <tr>
                <th>Source</th>
                <th>Provider</th>
                <th>Balance</th>
                <th>Currency</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {fundingAccounts.map(funding => (
                <tr key={funding.id}>
                  <td>
                    <strong>
                      {funding.name}
                    </strong>

                    {funding.demo && (
                      <span className="af-demo-badge">
                        DEMO
                      </span>
                    )}
                  </td>

                  <td>
                    {funding.provider}
                  </td>

                  <td>
                    <strong>
                      {Number(
                        funding.balance || 0
                      ).toLocaleString()}
                    </strong>
                  </td>

                  <td>
                    {funding.currency}
                  </td>

                  <td>
                    <span
                      className={
                        funding.status === 'ACTIVE'
                          ? 'af-status active'
                          : 'af-status'
                      }
                    >
                      {funding.status}
                    </span>
                  </td>

                  <td>
                    {funding.demo && (
                      <button
                        className="btn small secondary"
                        onClick={() =>
                          openFundingSimulator(funding)
                        }
                      >
                        Simulate Balance
                      </button>
                    )}
                  </td>
                </tr>
              ))}

              {!fundingAccounts.length && (
                <tr>
                  <td colSpan="6">
                    <div className="af-empty">
                      No funding sources yet.
                      Create one from a demo ad account.
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
        open={!!walletAccount}
        title="Create Demo Funding Wallet"
        onClose={() => {
          if (!saving) {
            setWalletAccount(null)
          }
        }}
      >
        <form onSubmit={createDemoWallet}>
          <div className="af-lock-box safe">
            <strong>Demo Wallet Only</strong>

            <span>
              This balance is simulated.
              No bank card or real money is used.
            </span>
          </div>

          <div className="field">
            <label>Wallet Name</label>

            <input
              required
              value={walletName}
              onChange={e =>
                setWalletName(e.target.value)
              }
            />
          </div>

          <div className="field">
            <label>Starting Balance</label>

            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={walletStartingBalance}
              onChange={e =>
                setWalletStartingBalance(
                  e.target.value
                )
              }
            />

            <small>
              Currency:
              {' '}
              {walletAccount?.currency || 'USD'}
            </small>
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              disabled={saving}
              onClick={() =>
                setWalletAccount(null)
              }
            >
              Cancel
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? 'Creating...'
                : 'Create Demo Wallet'}
            </button>
          </div>
        </form>
      </Modal>


      <Modal
        open={!!fundingSimulator}
        title="Funding Wallet Simulator"
        onClose={() => {
          if (!saving) {
            setFundingSimulator(null)
          }
        }}
      >
        <form onSubmit={saveFundingSimulator}>
          <div className="af-lock-box safe">
            <strong>Demo Funding Balance</strong>

            <span>
              Change the wallet balance to test
              insufficient-funds logic safely.
            </span>
          </div>

          {fundingSimulator && (
            <div className="connection-step-note">
              <strong>
                {fundingSimulator.name}
              </strong>

              <span>
                Current:
                {' '}
                {fundingSimulator.balance}
                {' '}
                {fundingSimulator.currency}
              </span>
            </div>
          )}

          <div className="field">
            <label>Funding Balance</label>

            <input
              type="number"
              min="0"
              step="0.01"
              required
              value={fundingSimBalance}
              onChange={e =>
                setFundingSimBalance(
                  e.target.value
                )
              }
            />
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() =>
                setFundingSimulator(null)
              }
            >
              Cancel
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              Apply Demo Balance
            </button>
          </div>
        </form>
      </Modal>


      <Modal
        open={!!topupAccount}
        title="Demo Manual Top-Up"
        onClose={() => {
          if (!saving) {
            setTopupAccount(null)
          }
        }}
      >
        <form onSubmit={saveDemoTopup}>
          <div className="af-lock-box safe">
            <strong>Demo Transaction Only</strong>

            <span>
              This simulates a successful funding
              transaction. No real money can move.
            </span>
          </div>

          {topupAccount && (
            <div className="connection-step-note">
              <strong>
                {topupAccount.name}
              </strong>

              <span>
                Ad balance:
                {' '}
                {topupAccount.balance}
                {' '}
                {topupAccount.currency}
              </span>

              <span>
                Funding source:
                {' '}
                {topupAccount.funding_source?.name || 'None'}
              </span>

              <span>
                Funding available:
                {' '}
                {topupAccount.funding_source?.balance || '0'}
                {' '}
                {topupAccount.funding_source?.currency || topupAccount.currency}
              </span>
            </div>
          )}

          <div className="field">
            <label>
              Top-Up Amount
            </label>

            <input
              type="number"
              min="0.01"
              step="0.01"
              required
              value={topupAmount}
              onChange={e =>
                setTopupAmount(
                  e.target.value
                )
              }
            />

            {topupAccount && (
              <small>
                Expected balance after top-up:
                {' '}
                {
                  (
                    Number(
                      topupAccount.balance || 0
                    ) +
                    Number(
                      topupAmount || 0
                    )
                  ).toFixed(2)
                }
                {' '}
                {topupAccount.currency}
              </small>
            )}
          </div>

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              disabled={saving}
              onClick={() =>
                setTopupAccount(null)
              }
            >
              Cancel
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? 'Processing...'
                : 'Complete Demo Top-Up'}
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
