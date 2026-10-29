# Type stubs for the parts of Bottle 0.13 that JamShoot Studio uses; Bottle ships none.

from collections.abc import Callable, Iterable
from typing import Any

class FormsDict(dict[str, Any]):
    def get(self, key: str, default: Any = None) -> Any: ...
    def getunicode(
        self, name: str, default: str | None = None, encoding: str | None = None
    ) -> str | None: ...

class BaseRequest:
    environ: dict[str, Any]
    @property
    def path(self) -> str: ...
    @property
    def query(self) -> FormsDict: ...
    @property
    def content_type(self) -> str: ...
    @property
    def content_length(self) -> int: ...

class BaseResponse:
    content_type: str
    @property
    def status_code(self) -> int: ...
    def set_header(self, name: str, value: str) -> None: ...

class HTTPResponse(BaseResponse, Exception):
    def __init__(
        self,
        body: Any = "",
        status: int | str | None = None,
        headers: dict[str, str] | None = None,
        **more_headers: Any,
    ) -> None: ...

class Bottle:
    def route(
        self, path: str, method: str = "GET", callback: Callable[..., Any] | None = None
    ) -> Any: ...
    def add_hook(self, name: str, func: Callable[[], None]) -> None: ...
    def error(self, code: int = 500) -> Callable[[Callable[..., Any]], Any]: ...
    def __call__(
        self, environ: dict[str, Any], start_response: Callable[..., Any]
    ) -> Iterable[bytes]: ...

request: BaseRequest
response: BaseResponse
