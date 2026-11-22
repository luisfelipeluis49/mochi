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


class InvalidRequestError(GatewayError):
    """The request is well-formed but asks for something that cannot be (422)."""

    status_code = 422


class ForbiddenError(GatewayError):
    """The caller is known but may not see this (403)."""

    status_code = 403
