"""How a pipeline says "this call failed in a way the page has a word for". The server turns one into the contract's
error reply and HTTP status. Anything else a pipeline raises is the contract's `server` error."""
from pulpermill.contract import BackendErrorKind


class Cancelled(Exception):
    """Raised inside inference when the writer pressed Stop (the client went away). The call changes nothing."""


class BackendError(Exception):
    """A failure with a contract kind. `detail` is plain words and is shown to the writer only for server and bad_request."""

    def __init__(self, kind: BackendErrorKind, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind
        self.detail = detail
