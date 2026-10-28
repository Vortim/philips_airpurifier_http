"""Blocking pyairctrl client helpers, run in the executor."""

import urllib.request
from types import SimpleNamespace

from pyairctrl import http_client
from pyairctrl.http_client import HTTPAirClient

from .const import PHILIPS_MAC_ADDRESS, PHILIPS_MODEL_NAME, REQUEST_TIMEOUT


class CannotConnect(Exception):
    """The purifier did not answer (offline, wrong IP, key exchange failed)."""


def _urlopen(url, data=None, timeout=REQUEST_TIMEOUT, **kwargs):
    return urllib.request.urlopen(url, data, timeout, **kwargs)


def _patch_request_timeout():
    """pyairctrl calls urlopen without a timeout, so an offline purifier blocks
    each request until the OS gives up (~2 minutes). Give its requests a timeout.
    """
    if getattr(http_client, "_timeout_patched", False):
        return
    http_client.urllib = SimpleNamespace(
        request=SimpleNamespace(urlopen=_urlopen, Request=urllib.request.Request)
    )
    http_client._timeout_patched = True


def connect(host):
    """Exchange a session key with the purifier and return a ready client."""
    _patch_request_timeout()
    try:
        return HTTPAirClient(host, False)
    except Exception as exc:
        raise CannotConnect(f"{host}: {exc}") from exc


def get_device_info(client):
    """Return the purifier's MAC address and model name (either may be None)."""
    try:
        wifi = client.get_wifi()
        firmware = client.get_firmware()
    except Exception as exc:
        raise CannotConnect(str(exc)) from exc
    mac = wifi.get(PHILIPS_MAC_ADDRESS)
    return {
        "mac": mac.lower() if mac else None,
        "model": firmware.get(PHILIPS_MODEL_NAME),
    }


def probe(host):
    """Connect to the purifier and read its identity, for the config flow."""
    return get_device_info(connect(host))
