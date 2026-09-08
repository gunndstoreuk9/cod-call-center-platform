from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://business-api.tiktok.com/open_api/v1.3"

AUTH_URL = "https://ads.tiktok.com/marketing_api/auth"


class TikTokAdsError(Exception):
    pass


def _request_json(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    payload: dict | None = None,
) -> dict:

    body = None

    request_headers = {
        "Accept": "application/json",
        **(headers or {}),
    }

    if payload is not None:
        body = json.dumps(
            payload
        ).encode("utf-8")

        request_headers[
            "Content-Type"
        ] = "application/json"

    request = Request(
        url,
        data=body,
        headers=request_headers,
        method=method,
    )

    try:
        with urlopen(
            request,
            timeout=20,
        ) as response:
            raw = response.read().decode(
                "utf-8"
            )

    except HTTPError as exc:
        try:
            raw = exc.read().decode(
                "utf-8"
            )
        except Exception:
            raw = ""

        raise TikTokAdsError(
            f"TikTok HTTP {exc.code}: "
            f"{raw[:500]}"
        ) from exc

    except URLError as exc:
        raise TikTokAdsError(
            f"TikTok connection failed: "
            f"{exc.reason}"
        ) from exc

    try:
        result = json.loads(raw)

    except json.JSONDecodeError as exc:
        raise TikTokAdsError(
            "TikTok returned invalid JSON"
        ) from exc

    code = result.get("code")

    if code not in (
        None,
        0,
    ):
        raise TikTokAdsError(
            result.get("message")
            or f"TikTok API error {code}"
        )

    return result.get(
        "data"
    ) or {}


def authorization_url(
    *,
    app_id: str,
    redirect_uri: str,
    state: str,
    scope: str | None = None,
) -> str:

    params = {
        "app_id": app_id,
        "state": state,
        "redirect_uri": redirect_uri,
    }

    # TikTok allows scope to be omitted.
    # Then all approved app permissions
    # are requested.
    if scope:
        params["scope"] = scope

    return (
        AUTH_URL
        + "?"
        + urlencode(params)
    )


def exchange_auth_code(
    *,
    app_id: str,
    app_secret: str,
    auth_code: str,
) -> dict:

    return _request_json(
        f"{API_BASE}/oauth2/access_token/",
        method="POST",
        payload={
            "app_id": app_id,
            "secret": app_secret,
            "auth_code": auth_code,
        },
    )


def authorized_advertisers(
    *,
    app_id: str,
    app_secret: str,
    access_token: str,
) -> dict:

    query = urlencode(
        {
            "app_id": app_id,
            "secret": app_secret,
        }
    )

    return _request_json(
        (
            f"{API_BASE}"
            f"/oauth2/advertiser/get/"
            f"?{query}"
        ),
        headers={
            "Access-Token":
                access_token,
        },
    )


def advertiser_ids_from_data(
    data: dict,
) -> list[str]:

    result = []

    direct = data.get(
        "advertiser_ids"
    )

    if isinstance(
        direct,
        list,
    ):
        result.extend(
            str(x)
            for x in direct
            if x
        )

    rows = (
        data.get("list")
        or data.get("advertisers")
        or []
    )

    if isinstance(rows, list):
        for row in rows:
            if isinstance(
                row,
                dict,
            ):
                value = (
                    row.get(
                        "advertiser_id"
                    )
                    or row.get("id")
                )
            else:
                value = row

            if value:
                result.append(
                    str(value)
                )

    return list(
        dict.fromkeys(result)
    )



def advertiser_info(
    *,
    access_token: str,
    advertiser_ids: list[str],
) -> list[dict]:

    if not advertiser_ids:
        return []

    fields = [
        "advertiser_id",
        "name",
        "currency",
        "status",
        "balance",
        "timezone",
        "owner_bc_id",
    ]

    query = urlencode(
        {
            "advertiser_ids":
                json.dumps(advertiser_ids),

            "fields":
                json.dumps(fields),
        }
    )

    data = _request_json(
        (
            f"{API_BASE}"
            f"/advertiser/info/"
            f"?{query}"
        ),
        headers={
            "Access-Token":
                access_token,
        },
    )

    rows = data.get("list") or []

    if not isinstance(rows, list):
        raise TikTokAdsError(
            "TikTok advertiser info response "
            "has an unexpected format"
        )

    return [
        row
        for row in rows
        if isinstance(row, dict)
    ]
