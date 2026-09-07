'use client'

import { useEffect, useMemo, useState } from 'react'
import { api, money } from '../../../lib/api'
import { useI18n } from '../../../lib/i18n'
import Modal from '../../../components/Modal'
import StatusBadge from '../../../components/StatusBadge'

const emptyProduct = {
  store_id: '',
  name: '',
  sku: '',
  image_url: '',
  selling_price: '',
  currency: 'MAD',
  default_qty: 1,
  delivery_product_ref: '',
  commission_per_confirmation: '5',
  status: 'ACTIVE'
}

const emptyOffer = {
  name: '',
  quantity: 1,
  price: '',
  commission_override: '',
  is_active: true
}

export default function ProductsPage() {
  const { t } = useI18n()

  const [products, setProducts] = useState([])
  const [stores, setStores] = useState([])

  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(emptyProduct)

  const [offersOpen, setOffersOpen] = useState(false)
  const [offerProduct, setOfferProduct] = useState(null)

  const [offerOpen, setOfferOpen] = useState(false)
  const [editingOffer, setEditingOffer] = useState(null)
  const [offerForm, setOfferForm] = useState(emptyOffer)

  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [saving, setSaving] = useState(false)
  const [savingOffer, setSavingOffer] = useState(false)

  const load = async () => {
    setError('')

    try {
      const [p, s] = await Promise.all([
        api('/products'),
        api('/stores')
      ])

      setProducts(p)
      setStores(s)

      if (!form.store_id && s[0]) {
        setForm(f => ({
          ...f,
          store_id: s[0].id
        }))
      }

      if (offerProduct) {
        const refreshed = p.find(
          x => x.id === offerProduct.id
        )

        if (refreshed) {
          setOfferProduct(refreshed)
        }
      }
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
    }, 3000)
  }

  const newProduct = () => {
    setEditing(null)

    setForm({
      ...emptyProduct,
      store_id: stores[0]?.id || ''
    })

    setOpen(true)
  }

  const editProduct = p => {
    setEditing(p)

    setForm({
      store_id: p.store_id,
      name: p.name,
      sku: p.sku,
      image_url: p.image_url || '',
      selling_price: p.selling_price,
      currency: p.currency,
      default_qty: p.default_qty,
      delivery_product_ref:
        p.delivery_product_ref || '',
      commission_per_confirmation:
        p.commission_per_confirmation ?? '',
      status: p.status
    })

    setOpen(true)
  }

  const submit = async e => {
    e.preventDefault()

    setSaving(true)
    setError('')

    try {
      const body = {
        ...form,
        selling_price:
          Number(form.selling_price),
        default_qty:
          Number(form.default_qty),
        commission_per_confirmation:
          form.commission_per_confirmation === ''
            ? null
            : Number(
                form.commission_per_confirmation
              ),
        delivery_product_ref:
          form.delivery_product_ref || null,
        image_url:
          form.image_url || null
      }

      if (editing) {
        await api(`/products/${editing.id}`, {
          method: 'PATCH',
          body
        })

        flash('Product updated successfully.')
      } else {
        const created = await api('/products', {
          method: 'POST',
          body: {
            ...body,
            offers: []
          }
        })

        flash(
          'Product created. Add its offers next.'
        )

        setOfferProduct(created)
        setOffersOpen(true)
      }

      setOpen(false)
      setEditing(null)

      await load()
    } catch (err) {
      setError(err.message)
    } finally {
      setSaving(false)
    }
  }

  const toggle = async p => {
    setError('')

    try {
      await api(`/products/${p.id}`, {
        method: 'PATCH',
        body: {
          status:
            p.status === 'ACTIVE'
              ? 'INACTIVE'
              : 'ACTIVE'
        }
      })

      flash(
        p.status === 'ACTIVE'
          ? 'Product disabled.'
          : 'Product enabled.'
      )

      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const manageOffers = p => {
    setOfferProduct(p)
    setOffersOpen(true)
  }

  const newOffer = () => {
    setEditingOffer(null)
    setOfferForm(emptyOffer)
    setOfferOpen(true)
  }

  const editOffer = offer => {
    setEditingOffer(offer)

    setOfferForm({
      name: offer.name,
      quantity: offer.quantity,
      price: offer.price,
      commission_override:
        offer.commission_override ?? '',
      is_active: !!offer.is_active
    })

    setOfferOpen(true)
  }

  const saveOffer = async e => {
    e.preventDefault()

    if (!offerProduct) return

    setSavingOffer(true)
    setError('')

    try {
      const body = {
        name: offerForm.name.trim(),
        quantity:
          Number(offerForm.quantity),
        price:
          Number(offerForm.price),
        commission_override:
          offerForm.commission_override === ''
            ? null
            : Number(
                offerForm.commission_override
              ),
        is_active:
          !!offerForm.is_active
      }

      if (editingOffer) {
        await api(
          `/products/${offerProduct.id}/offers/${editingOffer.id}`,
          {
            method: 'PATCH',
            body
          }
        )

        flash('Offer updated successfully.')
      } else {
        await api(
          `/products/${offerProduct.id}/offers`,
          {
            method: 'POST',
            body
          }
        )

        flash('Offer added successfully.')
      }

      setOfferOpen(false)
      setEditingOffer(null)
      setOfferForm(emptyOffer)

      await load()
    } catch (e) {
      setError(e.message)
    } finally {
      setSavingOffer(false)
    }
  }

  const toggleOffer = async offer => {
    if (!offerProduct) return

    setError('')

    try {
      await api(
        `/products/${offerProduct.id}/offers/${offer.id}`,
        {
          method: 'PATCH',
          body: {
            is_active: !offer.is_active
          }
        }
      )

      flash(
        offer.is_active
          ? 'Offer disabled.'
          : 'Offer enabled.'
      )

      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const deleteOffer = async offer => {
    if (!offerProduct) return

    const ok = window.confirm(
      `Delete offer "${offer.name}"?\n\n` +
      `If this offer was already used by an order, ` +
      `the system will block deletion and you should disable it instead.`
    )

    if (!ok) return

    setError('')

    try {
      await api(
        `/products/${offerProduct.id}/offers/${offer.id}`,
        {
          method: 'DELETE'
        }
      )

      flash('Offer deleted.')
      await load()
    } catch (e) {
      setError(e.message)
    }
  }

  const activeOffers = p =>
    (p.offers || []).filter(
      o => o.is_active
    ).length

  const sortedOffers = useMemo(() => {
    if (!offerProduct) return []

    return [...(offerProduct.offers || [])]
      .sort((a, b) => {
        if (a.quantity !== b.quantity) {
          return a.quantity - b.quantity
        }

        return String(a.name).localeCompare(
          String(b.name)
        )
      })
  }, [offerProduct])

  return (
    <>
      <div className="page-head">
        <div>
          <h1>{t('Products')}</h1>

          <p>
            Manage products, delivery references and
            the offers available to call-center agents.
          </p>
        </div>

        <button
          className="btn"
          onClick={newProduct}
        >
          {t('+ Add Product')}
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

      <div className="panel">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>{t('Product')}</th>
                <th>{t('SKU')}</th>
                <th>{t('Base Price')}</th>
                <th>{t('Delivery Ref')}</th>
                <th>{t('Commission')}</th>
                <th>{t('Offers')}</th>
                <th>{t('Status')}</th>
                <th>{t('Action')}</th>
              </tr>
            </thead>

            <tbody>
              {products.map(p => (
                <tr key={p.id}>
                  <td>
                    <strong>{p.name}</strong>

                    {p.image_url && (
                      <>
                        <br />
                        <small>
                          Image configured
                        </small>
                      </>
                    )}
                  </td>

                  <td>{p.sku}</td>

                  <td>
                    {money(
                      p.selling_price,
                      p.currency
                    )}
                  </td>

                  <td>
                    {p.delivery_product_ref || (
                      <small>
                        {t('Uses product name')}
                      </small>
                    )}
                  </td>

                  <td>
                    {p.commission_per_confirmation ==
                    null
                      ? t('Agent default')
                      : money(
                          p.commission_per_confirmation,
                          p.currency
                        )}
                  </td>

                  <td>
                    <button
                      type="button"
                      className="btn small secondary"
                      onClick={() =>
                        manageOffers(p)
                      }
                    >
                      {activeOffers(p)} active /{' '}
                      {p.offers?.length || 0}
                    </button>

                    {activeOffers(p) === 0 && (
                      <>
                        <br />
                        <small
                          style={{
                            color: '#b45309',
                            fontWeight: 700
                          }}
                        >
                          No active offers
                        </small>
                      </>
                    )}
                  </td>

                  <td>
                    <StatusBadge
                      value={p.status}
                    />
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
                          editProduct(p)
                        }
                      >
                        {t('Edit')}
                      </button>

                      <button
                        className="btn small secondary"
                        onClick={() =>
                          manageOffers(p)
                        }
                      >
                        Offers
                      </button>

                      <button
                        className="btn small secondary"
                        onClick={() =>
                          toggle(p)
                        }
                      >
                        {p.status === 'ACTIVE'
                          ? t('Disable')
                          : t('Enable')}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}

              {products.length === 0 && (
                <tr>
                  <td colSpan="8">
                    <div className="empty">
                      No products yet.
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* PRODUCT MODAL */}
      <Modal
        open={open}
        title={
          editing
            ? 'Edit Product'
            : 'Add Product'
        }
        onClose={() => setOpen(false)}
        wide
      >
        <form onSubmit={submit}>
          <div className="form-grid">

            <div className="field full">
              <label>{t('Store')}</label>

              <select
                required
                value={form.store_id}
                onChange={e =>
                  setForm({
                    ...form,
                    store_id:
                      e.target.value
                  })
                }
              >
                {stores.map(s => (
                  <option
                    key={s.id}
                    value={s.id}
                  >
                    {s.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label>
                {t('Product Name')}
              </label>

              <input
                required
                value={form.name}
                onChange={e =>
                  setForm({
                    ...form,
                    name:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('SKU')}</label>

              <input
                required
                value={form.sku}
                onChange={e =>
                  setForm({
                    ...form,
                    sku:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Base Selling Price')}
              </label>

              <input
                type="number"
                step="0.01"
                min="0"
                required
                value={form.selling_price}
                onChange={e =>
                  setForm({
                    ...form,
                    selling_price:
                      e.target.value
                  })
                }
              />

              <small>
                Agent offer prices are managed
                separately in Offers.
              </small>
            </div>

            <div className="field">
              <label>
                {t(
                  'Commission / Confirmation'
                )}
              </label>

              <input
                type="number"
                step="0.01"
                min="0"
                value={
                  form.commission_per_confirmation
                }
                onChange={e =>
                  setForm({
                    ...form,
                    commission_per_confirmation:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>{t('Currency')}</label>

              <input
                maxLength="3"
                value={form.currency}
                onChange={e =>
                  setForm({
                    ...form,
                    currency:
                      e.target.value.toUpperCase()
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                {t('Default Qty')}
              </label>

              <input
                type="number"
                min="1"
                value={form.default_qty}
                onChange={e =>
                  setForm({
                    ...form,
                    default_qty:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field full">
              <label>
                {t(
                  'Delivery Product Ref / Digylog Designation'
                )}
              </label>

              <input
                placeholder={t(
                  'Leave empty to send the product name'
                )}
                value={
                  form.delivery_product_ref
                }
                onChange={e =>
                  setForm({
                    ...form,
                    delivery_product_ref:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field full">
              <label>
                {t('Image URL (optional)')}
              </label>

              <input
                value={form.image_url}
                onChange={e =>
                  setForm({
                    ...form,
                    image_url:
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
              onClick={() =>
                setOpen(false)
              }
            >
              {t('Cancel')}
            </button>

            <button
              className="btn"
              disabled={saving}
            >
              {saving
                ? t('Saving...')
                : editing
                  ? t('Save Changes')
                  : t('Save Product')}
            </button>
          </div>
        </form>
      </Modal>

      {/* OFFERS MANAGER */}
      <Modal
        open={offersOpen}
        title={
          offerProduct
            ? `Offers — ${offerProduct.name}`
            : 'Offers'
        }
        onClose={() =>
          setOffersOpen(false)
        }
        wide
      >
        {offerProduct && (
          <>
            <div
              style={{
                display: 'flex',
                justifyContent:
                  'space-between',
                alignItems: 'center',
                gap: 12,
                marginBottom: 16,
                flexWrap: 'wrap'
              }}
            >
              <div>
                <strong
                  style={{
                    fontSize: 18
                  }}
                >
                  {offerProduct.name}
                </strong>

                <br />

                <small>
                  SKU: {offerProduct.sku} ·{' '}
                  {offerProduct.currency}
                </small>
              </div>

              <button
                className="btn"
                onClick={newOffer}
              >
                + Add Offer
              </button>
            </div>

            <div
              style={{
                padding: 12,
                borderRadius: 10,
                background: '#f8fafc',
                marginBottom: 14
              }}
            >
              <strong>
                Offers are the source of truth
                for Agent Workspace
              </strong>

              <br />

              <small>
                Selecting an offer will later set
                its quantity and total price
                automatically.
              </small>
            </div>

            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Offer</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Commission</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>

                <tbody>
                  {sortedOffers.map(offer => (
                    <tr key={offer.id}>
                      <td>
                        <strong>
                          {offer.name}
                        </strong>
                      </td>

                      <td>
                        × {offer.quantity}
                      </td>

                      <td>
                        <strong>
                          {money(
                            offer.price,
                            offerProduct.currency
                          )}
                        </strong>
                      </td>

                      <td>
                        {offer.commission_override ==
                        null
                          ? 'Product default'
                          : money(
                              offer.commission_override,
                              offerProduct.currency
                            )}
                      </td>

                      <td>
                        <StatusBadge
                          value={
                            offer.is_active
                              ? 'ACTIVE'
                              : 'DISABLED'
                          }
                        />
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
                              editOffer(offer)
                            }
                          >
                            Edit
                          </button>

                          <button
                            className="btn small secondary"
                            onClick={() =>
                              toggleOffer(offer)
                            }
                          >
                            {offer.is_active
                              ? 'Disable'
                              : 'Enable'}
                          </button>

                          <button
                            className="btn small danger"
                            onClick={() =>
                              deleteOffer(offer)
                            }
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}

                  {sortedOffers.length === 0 && (
                    <tr>
                      <td colSpan="6">
                        <div className="empty">
                          No offers yet.
                          Add the first offer for
                          this product.
                        </div>
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Modal>

      {/* ADD / EDIT OFFER */}
      <Modal
        open={offerOpen}
        title={
          editingOffer
            ? 'Edit Offer'
            : 'Add Offer'
        }
        onClose={() =>
          setOfferOpen(false)
        }
      >
        <form onSubmit={saveOffer}>
          <div className="form-grid">

            <div className="field full">
              <label>Offer Name</label>

              <input
                required
                maxLength="120"
                placeholder="Example: 2 Bottles"
                value={offerForm.name}
                onChange={e =>
                  setOfferForm({
                    ...offerForm,
                    name:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>Quantity</label>

              <input
                required
                type="number"
                min="1"
                max="1000"
                value={
                  offerForm.quantity
                }
                onChange={e =>
                  setOfferForm({
                    ...offerForm,
                    quantity:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field">
              <label>
                Offer Price
              </label>

              <input
                required
                type="number"
                min="0"
                step="0.01"
                value={offerForm.price}
                onChange={e =>
                  setOfferForm({
                    ...offerForm,
                    price:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field full">
              <label>
                Commission Override
                (optional)
              </label>

              <input
                type="number"
                min="0"
                step="0.01"
                placeholder="Leave empty to use product commission"
                value={
                  offerForm.commission_override
                }
                onChange={e =>
                  setOfferForm({
                    ...offerForm,
                    commission_override:
                      e.target.value
                  })
                }
              />
            </div>

            <div className="field full">
              <label className="check">
                <input
                  type="checkbox"
                  checked={
                    offerForm.is_active
                  }
                  onChange={e =>
                    setOfferForm({
                      ...offerForm,
                      is_active:
                        e.target.checked
                    })
                  }
                />

                Active offer — available to agents
              </label>
            </div>
          </div>

          {offerProduct && (
            <div
              style={{
                padding: 12,
                background: '#f8fafc',
                borderRadius: 10,
                marginTop: 8
              }}
            >
              <small>
                Product:{' '}
                <strong>
                  {offerProduct.name}
                </strong>
              </small>

              <br />

              <small>
                Preview:{' '}
                <strong>
                  {offerForm.name ||
                    'Offer'}{' '}
                  · ×
                  {offerForm.quantity ||
                    1}{' '}
                  ·{' '}
                  {offerForm.price !== ''
                    ? money(
                        Number(
                          offerForm.price
                        ),
                        offerProduct.currency
                      )
                    : '—'}
                </strong>
              </small>
            </div>
          )}

          <div className="form-actions">
            <button
              type="button"
              className="btn secondary"
              onClick={() =>
                setOfferOpen(false)
              }
            >
              Cancel
            </button>

            <button
              className="btn"
              disabled={savingOffer}
            >
              {savingOffer
                ? 'Saving...'
                : editingOffer
                  ? 'Save Offer'
                  : 'Add Offer'}
            </button>
          </div>
        </form>
      </Modal>
    </>
  )
}
