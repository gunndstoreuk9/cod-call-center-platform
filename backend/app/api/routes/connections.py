from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.deps import require_roles
from app.core.time import utcnow
from app.models import (
    AdAccount,
    AdSyncRun,
    IntegrationConfig,
    Store,
    User,
)
from app.services.audit import log_action
from app.services.integration_crypto import (
    decrypt_secret_dict,
    encrypt_secret_dict,
)

from app.services.tiktok_ads import (
    TikTokAdsError,
    advertiser_ids_from_data,
    advertiser_info,
    authorization_url,
    authorized_advertisers,
    exchange_auth_code,
)


router = APIRouter(
    prefix="/connections",
    tags=["connections"],
)


PROVIDERS = {
    "TIKTOK_ADS": {
        "provider": "TIKTOK_ADS",
        "label": "TikTok Ads",
        "category": "ADS",
        "enabled": True,
        "status": "ENABLED",
        "setup_mode": "OAUTH_APP",
        "supports_oauth": True,
        "supports_account_import": True,
        "supports_balance_sync": True,
        "supports_spend_sync": True,
        "supports_funding": True,
    },

    "SLASH": {
        "provider": "SLASH",
        "label": "Slash",
        "category": "FUNDING",
        "enabled": False,
        "status": "COMING_NEXT",
        "setup_mode": "API",
        "supports_oauth": False,
        "supports_account_import": True,
        "supports_balance_sync": True,
        "supports_spend_sync": False,
        "supports_funding": True,
    },

    "META_ADS": {
        "provider": "META_ADS",
        "label": "Meta Ads",
        "category": "ADS",
        "enabled": False,
        "status": "FUTURE",
        "setup_mode": "OAUTH_APP",
        "supports_oauth": True,
        "supports_account_import": True,
        "supports_balance_sync": False,
        "supports_spend_sync": True,
        "supports_funding": False,
    },

    "GOOGLE_ADS": {
        "provider": "GOOGLE_ADS",
        "label": "Google Ads",
        "category": "ADS",
        "enabled": False,
        "status": "FUTURE",
        "setup_mode": "OAUTH_APP",
        "supports_oauth": True,
        "supports_account_import": True,
        "supports_balance_sync": False,
        "supports_spend_sync": True,
        "supports_funding": False,
    },
}


class ConnectionCreate(BaseModel):
    provider: str
    name: str = Field(min_length=1, max_length=140)
    store_id: str | None = None
    config: dict = Field(default_factory=dict)
    secrets: dict = Field(default_factory=dict)


class ConnectionUpdate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=140,
    )

    store_id: str | None = None
    is_active: bool | None = None

    config: dict | None = None
    secrets: dict | None = None

    remove_secret_keys: list[str] = Field(
        default_factory=list
    )



def _b64_encode(raw: bytes) -> str:
    return (
        base64.urlsafe_b64encode(raw)
        .decode("ascii")
        .rstrip("=")
    )


def _b64_decode(value: str) -> bytes:
    padding = "=" * (
        (-len(value)) % 4
    )

    return base64.urlsafe_b64decode(
        value + padding
    )


def _oauth_state(
    connection_id: str,
) -> str:

    payload = {
        "cid": connection_id,
        "nonce":
            secrets.token_urlsafe(16),
        "exp":
            int(time.time()) + 900,
    }

    encoded = _b64_encode(
        json.dumps(
            payload,
            separators=(",", ":"),
        ).encode("utf-8")
    )

    signature = hmac.new(
        settings.app_secret.encode(
            "utf-8"
        ),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    return (
        encoded
        + "."
        + signature
    )


def _parse_oauth_state(
    value: str,
) -> str:

    try:
        encoded, signature = (
            value.split(".", 1)
        )

    except ValueError:
        raise HTTPException(
            400,
            "Invalid OAuth state",
        )

    expected = hmac.new(
        settings.app_secret.encode(
            "utf-8"
        ),
        encoded.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(
        signature,
        expected,
    ):
        raise HTTPException(
            400,
            "Invalid OAuth state",
        )

    try:
        payload = json.loads(
            _b64_decode(
                encoded
            ).decode("utf-8")
        )

    except Exception:
        raise HTTPException(
            400,
            "Invalid OAuth state",
        )

    if int(
        payload.get("exp") or 0
    ) < int(time.time()):
        raise HTTPException(
            400,
            "OAuth state expired",
        )

    connection_id = str(
        payload.get("cid")
        or ""
    )

    if not connection_id:
        raise HTTPException(
            400,
            "Invalid OAuth state",
        )

    return connection_id


def _tiktok_callback_url() -> str:
    return (
        settings.public_api_base_url
        .rstrip("/")
        + "/api/v1/connections/"
          "tiktok/callback"
    )


def normalize_provider(value: str) -> str:
    provider = (value or "").strip().upper()

    if provider not in PROVIDERS:
        raise HTTPException(
            400,
            "Unsupported connection provider",
        )

    return provider


def connection_or_404(
    db: Session,
    connection_id: str,
) -> IntegrationConfig:

    row = (
        db.query(IntegrationConfig)
        .filter(
            IntegrationConfig.id == connection_id,
            IntegrationConfig.provider.in_(
                list(PROVIDERS.keys())
            ),
        )
        .first()
    )

    if not row:
        raise HTTPException(
            404,
            "Connection not found",
        )

    return row


def secret_values(
    row: IntegrationConfig,
) -> dict:

    if not row.secrets_encrypted:
        return {}

    try:
        return decrypt_secret_dict(
            row.secrets_encrypted
        )

    except Exception as exc:
        raise HTTPException(
            500,
            "Connection credentials cannot be decrypted. "
            "APP_SECRET may have changed.",
        ) from exc


def connection_status(
    row: IntegrationConfig,
    secrets: dict,
) -> str:

    if not row.is_active:
        return "DISCONNECTED"

    if row.last_test_status == "SUCCESS":
        return "CONNECTED"

    if secrets:
        return "CONFIGURED"

    return "DRAFT"


def connection_out(
    row: IntegrationConfig,
) -> dict:

    secrets = secret_values(row)

    definition = PROVIDERS.get(
        row.provider,
        {}
    )

    return {
        "id": row.id,
        "provider": row.provider,
        "provider_label": definition.get(
            "label",
            row.provider,
        ),
        "category": definition.get(
            "category"
        ),

        "name": row.name,
        "store_id": row.store_id,
        "is_active": row.is_active,

        "status": connection_status(
            row,
            secrets,
        ),

        "config": row.config or {},

        # NEVER return credential values.
        "secret_keys": sorted(
            secrets.keys()
        ),

        "has_credentials": bool(
            secrets
        ),

        "last_test_status":
            row.last_test_status,

        "last_test_message":
            row.last_test_message,

        "last_test_at":
            row.last_test_at,

        "created_at":
            row.created_at,

        "updated_at":
            row.updated_at,
    }


@router.get("/providers")
def list_connection_providers(
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    return list(
        PROVIDERS.values()
    )


@router.get("")
def list_connections(
    provider: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    q = db.query(
        IntegrationConfig
    ).filter(
        IntegrationConfig.provider.in_(
            list(PROVIDERS.keys())
        )
    )

    if provider:
        q = q.filter(
            IntegrationConfig.provider
            == normalize_provider(provider)
        )

    rows = (
        q.order_by(
            IntegrationConfig.created_at.desc()
        )
        .all()
    )

    return [
        connection_out(row)
        for row in rows
    ]


@router.get("/{connection_id}")
def get_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    return connection_out(
        connection_or_404(
            db,
            connection_id,
        )
    )


@router.post("")
def create_connection(
    payload: ConnectionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    provider = normalize_provider(
        payload.provider
    )

    provider_definition = PROVIDERS[
        provider
    ]

    if not provider_definition[
        "enabled"
    ]:
        raise HTTPException(
            400,
            f"{provider_definition['label']} "
            "connection is not enabled yet",
        )

    name = payload.name.strip()

    if not name:
        raise HTTPException(
            400,
            "Connection name is required",
        )

    if payload.store_id:
        store = (
            db.query(Store)
            .filter(
                Store.id
                == payload.store_id
            )
            .first()
        )

        if not store:
            raise HTTPException(
                400,
                "Invalid store",
            )

    secrets = {
        str(key): value
        for key, value
        in (payload.secrets or {}).items()
        if value not in (
            None,
            "",
        )
    }

    row = IntegrationConfig(
        provider=provider,
        name=name,
        store_id=payload.store_id,
        is_active=True,
        config=dict(
            payload.config or {}
        ),

        secrets_encrypted=(
            encrypt_secret_dict(
                secrets
            )
            if secrets
            else None
        ),

        created_by_user_id=user.id,

        last_test_status=(
            "NOT_TESTED"
            if secrets
            else "NOT_CONFIGURED"
        ),

        last_test_message=None,
        last_test_at=None,
    )

    db.add(row)
    db.flush()

    log_action(
        db,
        user_id=user.id,
        action="CONNECTION_CREATED",
        entity_type="INTEGRATION",
        entity_id=row.id,
        after={
            "provider": provider,
            "name": row.name,
            "store_id": row.store_id,

            # Only keys, never values.
            "secret_keys": sorted(
                secrets.keys()
            ),
        },
    )

    db.commit()
    db.refresh(row)

    return connection_out(row)


@router.patch("/{connection_id}")
def update_connection(
    connection_id: str,
    payload: ConnectionUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    row = connection_or_404(
        db,
        connection_id,
    )

    updates = payload.model_dump(
        exclude_unset=True
    )

    before = {
        "name": row.name,
        "store_id": row.store_id,
        "is_active": row.is_active,
        "config": row.config or {},
    }

    setup_changed = False

    if "name" in updates:
        name = str(
            updates.pop("name")
            or ""
        ).strip()

        if not name:
            raise HTTPException(
                400,
                "Connection name is required",
            )

        row.name = name

    if "store_id" in updates:
        store_id = updates.pop(
            "store_id"
        )

        if store_id:
            store = (
                db.query(Store)
                .filter(
                    Store.id == store_id
                )
                .first()
            )

            if not store:
                raise HTTPException(
                    400,
                    "Invalid store",
                )

        row.store_id = store_id

    if "is_active" in updates:
        row.is_active = bool(
            updates.pop(
                "is_active"
            )
        )

    if "config" in updates:
        incoming = (
            updates.pop("config")
            or {}
        )

        merged = dict(
            row.config or {}
        )

        merged.update(
            incoming
        )

        row.config = merged
        setup_changed = True

    current_secrets = secret_values(
        row
    )

    if "secrets" in updates:
        incoming = (
            updates.pop("secrets")
            or {}
        )

        for key, value in incoming.items():
            if value not in (
                None,
                "",
            ):
                current_secrets[
                    str(key)
                ] = value

        setup_changed = True

    remove_keys = updates.pop(
        "remove_secret_keys",
        [],
    )

    for key in remove_keys:
        current_secrets.pop(
            key,
            None,
        )

        setup_changed = True

    row.secrets_encrypted = (
        encrypt_secret_dict(
            current_secrets
        )
        if current_secrets
        else None
    )

    if setup_changed:
        row.last_test_status = (
            "NOT_TESTED"
            if current_secrets
            else "NOT_CONFIGURED"
        )

        row.last_test_message = None
        row.last_test_at = None

    log_action(
        db,
        user_id=user.id,
        action="CONNECTION_UPDATED",
        entity_type="INTEGRATION",
        entity_id=row.id,
        before=before,
        after={
            "name": row.name,
            "store_id": row.store_id,
            "is_active": row.is_active,
            "config": row.config or {},

            # No credential values.
            "secret_keys": sorted(
                current_secrets.keys()
            ),
        },
    )

    db.commit()
    db.refresh(row)

    return connection_out(row)


@router.post("/{connection_id}/disconnect")
def disconnect_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    row = connection_or_404(
        db,
        connection_id,
    )

    row.is_active = False
    row.last_test_status = (
        "DISCONNECTED"
    )

    row.last_test_message = (
        "Connection disabled from CODOPS"
    )

    row.last_test_at = utcnow()

    log_action(
        db,
        user_id=user.id,
        action="CONNECTION_DISCONNECTED",
        entity_type="INTEGRATION",
        entity_id=row.id,
        after={
            "provider": row.provider,
            "name": row.name,
        },
    )

    db.commit()
    db.refresh(row)

    return connection_out(row)


@router.post("/{connection_id}/enable")
def enable_connection(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    row = connection_or_404(
        db,
        connection_id,
    )

    row.is_active = True

    credentials = secret_values(row)

    row.last_test_status = (
        "NOT_TESTED"
        if credentials
        else "NOT_CONFIGURED"
    )

    row.last_test_message = None
    row.last_test_at = None

    log_action(
        db,
        user_id=user.id,
        action="CONNECTION_ENABLED",
        entity_type="INTEGRATION",
        entity_id=row.id,
        after={
            "provider": row.provider,
            "name": row.name,
        },
    )

    db.commit()
    db.refresh(row)

    return connection_out(row)



@router.post(
    "/{connection_id}/tiktok/authorize"
)
def start_tiktok_authorization(
    connection_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    row = connection_or_404(
        db,
        connection_id,
    )

    if row.provider != "TIKTOK_ADS":
        raise HTTPException(
            400,
            "Connection is not TikTok Ads",
        )

    if not row.is_active:
        raise HTTPException(
            400,
            "Connection is disabled",
        )

    config = dict(
        row.config or {}
    )

    secrets_data = secret_values(
        row
    )

    app_id = str(
        config.get("app_id")
        or ""
    ).strip()

    app_secret = str(
        secrets_data.get(
            "app_secret"
        )
        or ""
    ).strip()

    if not app_id:
        raise HTTPException(
            400,
            "TikTok App ID is required",
        )

    if not app_secret:
        raise HTTPException(
            400,
            "TikTok App Secret is required",
        )

    callback_url = (
        _tiktok_callback_url()
    )

    state = _oauth_state(
        row.id
    )

    url = authorization_url(
        app_id=app_id,
        redirect_uri=callback_url,
        state=state,
        scope=(
            str(
                config.get("scope")
                or ""
            ).strip()
            or None
        ),
    )

    return {
        "authorization_url": url,
        "callback_url": callback_url,
    }


@router.get(
    "/tiktok/callback",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def tiktok_oauth_callback(
    auth_code: str | None = None,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    if not auth_code or not state:
        return HTMLResponse(
            """
            <html>
            <body style="
              font-family:Arial,sans-serif;
              padding:40px;
            ">
            <h2>TikTok connection failed</h2>
            <p>Missing authorization response.</p>
            </body>
            </html>
            """,
            status_code=400,
        )

    connection_id = (
        _parse_oauth_state(
            state
        )
    )

    row = connection_or_404(
        db,
        connection_id,
    )

    if row.provider != "TIKTOK_ADS":
        raise HTTPException(
            400,
            "Invalid TikTok connection",
        )

    config = dict(
        row.config or {}
    )

    secrets_data = secret_values(
        row
    )

    app_id = str(
        config.get("app_id")
        or ""
    ).strip()

    app_secret = str(
        secrets_data.get(
            "app_secret"
        )
        or ""
    ).strip()

    try:
        token_data = exchange_auth_code(
            app_id=app_id,
            app_secret=app_secret,
            auth_code=auth_code,
        )

        access_token = str(
            token_data.get(
                "access_token"
            )
            or ""
        ).strip()

        if not access_token:
            raise TikTokAdsError(
                "TikTok access token missing"
            )

        advertiser_data = (
            authorized_advertisers(
                app_id=app_id,
                app_secret=app_secret,
                access_token=access_token,
            )
        )

        advertiser_ids = (
            advertiser_ids_from_data(
                advertiser_data
            )
        )

    except TikTokAdsError as exc:
        row.last_test_status = "FAILED"
        row.last_test_message = str(exc)
        row.last_test_at = utcnow()

        db.commit()

        return HTMLResponse(
            f"""
            <html>
            <body style="
              font-family:Arial,sans-serif;
              padding:40px;
            ">
            <h2>TikTok connection failed</h2>
            <p>{str(exc)}</p>
            </body>
            </html>
            """,
            status_code=400,
        )

    secrets_data[
        "access_token"
    ] = access_token

    if token_data.get(
        "refresh_token"
    ):
        secrets_data[
            "refresh_token"
        ] = token_data[
            "refresh_token"
        ]

    row.secrets_encrypted = (
        encrypt_secret_dict(
            secrets_data
        )
    )

    config[
        "authorized_advertiser_ids"
    ] = advertiser_ids

    if token_data.get("scope"):
        config["authorized_scope"] = (
            token_data["scope"]
        )

    config[
        "oauth_connected_at"
    ] = utcnow().isoformat()

    row.config = config

    row.last_test_status = "SUCCESS"
    row.last_test_message = (
        f"TikTok connected. "
        f"{len(advertiser_ids)} "
        f"ad account(s) authorized."
    )

    row.last_test_at = utcnow()
    row.is_active = True

    db.commit()

    return HTMLResponse(
        f"""
        <html>
        <body style="
          font-family:Arial,sans-serif;
          max-width:620px;
          margin:60px auto;
          padding:30px;
        ">
          <h2>CODOPS × TikTok connected ✓</h2>
          <p>
            {len(advertiser_ids)}
            ad account(s) authorized.
          </p>
          <p>
            You can close this window
            and return to CODOPS.
          </p>
        </body>
        </html>
        """
    )


@router.get(
    "/{connection_id}/tiktok/accounts"
)
def tiktok_authorized_accounts(
    connection_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    row = connection_or_404(
        db,
        connection_id,
    )

    if row.provider != "TIKTOK_ADS":
        raise HTTPException(
            400,
            "Connection is not TikTok Ads",
        )

    config = dict(
        row.config or {}
    )

    return {
        "connection_id": row.id,
        "connected":
            row.last_test_status
            == "SUCCESS",

        "advertiser_ids":
            config.get(
                "authorized_advertiser_ids"
            )
            or [],
    }



@router.post(
    "/{connection_id}/tiktok/import-accounts"
)
def import_tiktok_accounts(
    connection_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
        )
    ),
):
    row = connection_or_404(
        db,
        connection_id,
    )

    if row.provider != "TIKTOK_ADS":
        raise HTTPException(
            400,
            "Connection is not TikTok Ads",
        )

    if (
        row.last_test_status
        != "SUCCESS"
    ):
        raise HTTPException(
            400,
            "Connect TikTok before importing accounts",
        )

    config = dict(
        row.config or {}
    )

    authorized_ids = [
        str(x)
        for x in (
            config.get(
                "authorized_advertiser_ids"
            )
            or []
        )
        if x
    ]

    if not authorized_ids:
        raise HTTPException(
            400,
            "No authorized TikTok ad accounts found",
        )

    credentials = secret_values(
        row
    )

    access_token = str(
        credentials.get(
            "access_token"
        )
        or ""
    ).strip()

    if not access_token:
        raise HTTPException(
            400,
            "TikTok access token is missing. Reconnect TikTok.",
        )

    sync = AdSyncRun(
        integration_id=row.id,
        provider="TIKTOK_ADS",
        sync_type="ACCOUNT_IMPORT",
        status="RUNNING",
        accounts_scanned=len(
            authorized_ids
        ),
        accounts_updated=0,
        started_at=utcnow(),
        created_at=utcnow(),
    )

    db.add(sync)
    db.flush()

    try:
        details = advertiser_info(
            access_token=access_token,
            advertiser_ids=authorized_ids,
        )

        detail_map = {
            str(
                item.get("advertiser_id")
                or ""
            ): item
            for item in details
            if item.get("advertiser_id")
        }

        imported = []

        for advertiser_id in authorized_ids:

            info = detail_map.get(
                advertiser_id,
                {}
            )

            account = (
                db.query(AdAccount)
                .filter(
                    AdAccount.provider
                    == "TIKTOK_ADS",

                    AdAccount.external_account_id
                    == advertiser_id,
                )
                .first()
            )

            if not account:
                account = AdAccount(
                    provider="TIKTOK_ADS",
                    external_account_id=
                        advertiser_id,
                )

                db.add(account)

            account.integration_id = row.id
            account.store_id = row.store_id

            account.external_business_id = (
                str(
                    info.get("owner_bc_id")
                    or ""
                )
                or None
            )

            account.name = (
                str(
                    info.get("name")
                    or advertiser_id
                )
            )

            account.currency = (
                str(
                    info.get("currency")
                    or "USD"
                )
            )

            try:
                account.current_balance = (
                    info.get("balance")
                    or 0
                )
            except Exception:
                account.current_balance = 0

            account.status = (
                str(
                    info.get("status")
                    or "UNKNOWN"
                )
            )

            account.is_active = True

            account.provider_payload = {
                "timezone":
                    info.get("timezone"),

                "owner_bc_id":
                    info.get("owner_bc_id"),
            }

            account.balance_synced_at = (
                utcnow()
            )

            account.last_error = None

            imported.append(account)

        db.flush()

        sync.accounts_updated = len(
            imported
        )

        sync.status = "SUCCESS"
        sync.finished_at = utcnow()

        row.last_test_status = "SUCCESS"
        row.last_test_message = (
            f"TikTok connected. "
            f"{len(imported)} ad account(s) imported."
        )

        row.last_test_at = utcnow()

        log_action(
            db,
            user_id=user.id,
            action="TIKTOK_AD_ACCOUNTS_IMPORTED",
            entity_type="INTEGRATION",
            entity_id=row.id,
            after={
                "count":
                    len(imported),

                "advertiser_ids":
                    authorized_ids,
            },
        )

        db.commit()

        return {
            "ok": True,

            "imported":
                len(imported),

            "accounts": [
                {
                    "id":
                        account.id,

                    "advertiser_id":
                        account.external_account_id,

                    "name":
                        account.name,

                    "currency":
                        account.currency,

                    "balance":
                        str(
                            account.current_balance
                        ),

                    "status":
                        account.status,

                    "business_center_id":
                        account.external_business_id,

                    "balance_synced_at":
                        account.balance_synced_at,
                }
                for account in imported
            ],
        }

    except TikTokAdsError as exc:
        sync.status = "FAILED"
        sync.error = str(exc)
        sync.finished_at = utcnow()

        row.last_test_status = "FAILED"
        row.last_test_message = str(exc)
        row.last_test_at = utcnow()

        db.commit()

        raise HTTPException(
            400,
            str(exc),
        )


@router.get(
    "/{connection_id}/tiktok/imported-accounts"
)
def list_imported_tiktok_accounts(
    connection_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(
        require_roles(
            "OWNER",
            "ADMIN",
            "SUPERVISOR",
        )
    ),
):
    row = connection_or_404(
        db,
        connection_id,
    )

    if row.provider != "TIKTOK_ADS":
        raise HTTPException(
            400,
            "Connection is not TikTok Ads",
        )

    accounts = (
        db.query(AdAccount)
        .filter(
            AdAccount.integration_id
            == row.id,

            AdAccount.provider
            == "TIKTOK_ADS",
        )
        .order_by(
            AdAccount.name.asc()
        )
        .all()
    )

    return [
        {
            "id":
                account.id,

            "advertiser_id":
                account.external_account_id,

            "name":
                account.name,

            "currency":
                account.currency,

            "balance":
                str(
                    account.current_balance
                ),

            "status":
                account.status,

            "business_center_id":
                account.external_business_id,

            "store_id":
                account.store_id,

            "balance_synced_at":
                account.balance_synced_at,

            "is_active":
                account.is_active,
        }
        for account in accounts
    ]
