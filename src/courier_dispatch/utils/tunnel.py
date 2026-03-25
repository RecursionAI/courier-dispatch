"""ngrok tunnel management for Courier Dispatch."""

import logging

import ngrok

logger = logging.getLogger("courier-dispatch")


def start_tunnel(port: int, authtoken: str, domain: str | None = None) -> str:
    """Start an ngrok tunnel forwarding to the given port.

    Returns the public URL.
    """
    kwargs = {"addr": port, "authtoken": authtoken}
    if domain:
        kwargs["domain"] = domain

    listener = ngrok.forward(**kwargs)
    url = listener.url()
    logger.info(f"ngrok tunnel established: {url}")
    return url
