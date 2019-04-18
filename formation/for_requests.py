import requests
from requests.compat import urljoin
from .formation import wrap, _REQ_HTTP, _RES_HTTP, _SESSION
from attr import attrib, attrs
from lxml import html
from toolz.curried import keyfilter, reduce
import xmltodict
import datetime

__all__ = ["build_sender", "build", "client"]


def client(cls=None):
    def client_decorator(cls):
        original_init = cls.__init__

        def now_iso(self):
            return datetime.datetime.utcnow().isoformat()

        def path(self, p):
            return requests.compat.urljoin(self.base_uri, p)

        def init(self, *args, **kwargs):
            original_init(self, *args, **kwargs)
            base_uri = kwargs.get(
                "base_uri", getattr(self.__class__, "base_uri", "http://localhost")
            )
            response_as = kwargs.get(
                "response_as", getattr(self.__class__, "response_as", None)
            )
            self.request = build(
                middleware=kwargs.get(
                    "middleware", getattr(self.__class__, "middleware", [])
                ),
                base_uri=base_uri,
                response_as=response_as,
            )

            self.base_uri = base_uri

        cls.path = path
        cls.now_iso = now_iso
        cls.__init__ = init
        return cls

    if cls:
        return client_decorator(cls)
    return client_decorator


@attrs
class FormationHttpRequest(object):
    url = attrib()
    method = attrib(default="get")
    headers = attrib(default={})
    params = attrib(default={})
    auth = attrib(default=None)
    data = attrib(default=None)
    timeout = attrib(default=None)
    allow_redirects = attrib(default=True)

def params_filter(p):
    return p.startswith(":")


def not_params_filter(p):
    return not params_filter(p)


def apply_params(url, params):
    route_params = keyfilter(params_filter, params)
    return (
        reduce(lambda acc, kv: acc.replace(kv[0], kv[1]), route_params.items(), url),
        keyfilter(not_params_filter, params),
    )


def get_response(ctx):
    return ctx.get(_RES_HTTP, None)


@staticmethod
def raw_response(ctx):
    res = get_response(ctx)
    if not res:
        return (None, None, None)
    return (res, res.status_code, res.headers)


@staticmethod
def json_response(ctx):
    res = get_response(ctx)
    if not res:
        return (None, None, None)
    return (res.json(), res.status_code, res.headers)


@staticmethod
def xmltodict_response(ctx):
    res = get_response(ctx)
    if not res:
        return (None, None, None)
    return (xmltodict.parse(res.text), res.status_code, res.headers)


@staticmethod
def html_response(ctx):
    res = get_response(ctx)
    if not res:
        return (None, None, None)
    return (html.fromstring(res.content), res.status_code, res.headers)


@staticmethod
def text_response(ctx):
    res = get_response(ctx)
    if not res:
        return (None, None, None)
    return (res.text, res.status_code, res.headers)


def build_sender(middleware=[], base_uri=None, response_as=None):
    wrapped = wrap(requests_adapter, middleware=middleware)

    def sender(method, url, session_context={}, params={}, **kwargs):
        resolved_response_as = kwargs.get("response_as", response_as) or raw_response
        params = params if isinstance(params, dict) else params.to_dict()
        (url, params) = apply_params(url, params)
        ctx = {
            _REQ_HTTP: FormationHttpRequest(
                url=urljoin(base_uri, url), method=method, params=params, **kwargs
            ),
            _SESSION: session_context,
        }
        ctx = wrapped(ctx)
        return resolved_response_as(ctx)

    return sender


class Sender(object):
    def __init__(self, send):
        self.send = send

    def get(self, path, **kwargs):
        return self.send("get", path, **kwargs)

    def post(self, path, **kwargs):
        return self.send("post", path, **kwargs)

    def put(self, path, **kwargs):
        return self.send("put", path, **kwargs)


def build(middleware=[], base_uri=None, response_as=None):
    return Sender(
        build_sender(middleware=middleware, base_uri=base_uri, response_as=response_as)
    )


# TODO: timeout (middleware)
# TODO: pass more requests vars via req (e.g. timeout, retry)


def requests_adapter(ctx):
    req = ctx[_REQ_HTTP]
    meth = getattr(requests, req.method.lower())
    # TODO ship var as kwargs and not explicitly

    res = meth(
        req.url,
        headers=req.headers,
        params=req.params,
        auth=req.auth,
        data=req.data,
        timeout=req.timeout,
        allow_redirects=req.allow_redirects
    )
    ctx[_RES_HTTP] = res
    return ctx
