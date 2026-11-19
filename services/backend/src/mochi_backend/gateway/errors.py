"""Errors the routes turn into HTTP statuses."""


class GatewayError(Exception):
    """Base class; `status_code` is what the HTTP edge answers."""

    status_code = 500


class ConflictError(GatewayError):
    """The request cannot apply to the current state (409)."""

    status_code = 409


class UpstreamError(GatewayError):
    """Agora (or another upstream) failed (502)."""

    status_code = 502


class NotFoundError(GatewayError):
    """Unknown resource, such as a device id (404)."""

    status_code = 404
