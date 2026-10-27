"""Shadowsocks：SIP002（ss://b64(method:pass)@host:port/?plugin=...#name）与旧式全 base64 格式。"""

from urllib.parse import parse_qs, quote, unquote

from routeforge.ir.node import SSNode
from routeforge.parsers.errors import ParseError
from routeforge.parsers.uri._common import b64decode_loose, b64encode_text, host_for_uri, split_hostport


def parse(uri: str) -> SSNode:
    body = uri.strip().removeprefix("ss://")
    body, _, frag = body.partition("#")
    main, _, qs = body.partition("?")
    main = main.rstrip("/")
    if "@" in main:
        userinfo, _, hostport = main.rpartition("@")
        userinfo = unquote(userinfo)
        if ":" not in userinfo:
            userinfo = b64decode_loose(userinfo)
    else:
        userinfo, _, hostport = b64decode_loose(main).rpartition("@")
    cipher, sep, password = userinfo.partition(":")
    if not sep or not cipher:
        raise ParseError("ss：缺少 加密方式:密码")
    server, port = split_hostport(hostport)
    params = {k: v[-1] for k, v in parse_qs(qs).items()}
    plugin, opts = _parse_plugin(params.get("plugin", ""))
    return SSNode(
        name=unquote(frag) or f"{server}:{port}",
        server=server,
        port=port,
        cipher=cipher,
        password=password,
        plugin=plugin,
        plugin_opts=opts,
    )


def dump(node: SSNode) -> str:
    userinfo = b64encode_text(f"{node.cipher}:{node.password}", urlsafe=True, padding=False)
    uri = f"ss://{userinfo}@{host_for_uri(node.server)}:{node.port}"
    if node.plugin:
        uri += "/?plugin=" + quote(_dump_plugin(node), safe="")
    return uri + "#" + quote(node.name, safe="")


def _parse_plugin(raw: str) -> tuple[str | None, dict[str, str | bool]]:
    if not raw:
        return None, {}
    name, *parts = raw.split(";")
    opts: dict[str, str | bool] = {}
    for part in parts:
        key, sep, value = part.partition("=")
        opts[key] = value if sep else True
    if name in ("obfs-local", "simple-obfs", "obfs"):
        out: dict[str, str | bool] = {"mode": opts.get("obfs", "http")}
        if opts.get("obfs-host"):
            out["host"] = opts["obfs-host"]
        return "obfs", out
    if name == "v2ray-plugin":
        out = {"mode": opts.get("mode", "websocket")}
        if opts.get("tls"):
            out["tls"] = True
        for key in ("host", "path"):
            if opts.get(key):
                out[key] = opts[key]
        return "v2ray-plugin", out
    raise ParseError(f"ss：不支持的插件 {name}")


def _dump_plugin(node: SSNode) -> str:
    o = node.plugin_opts
    if node.plugin == "obfs":
        parts = ["obfs-local", f"obfs={o.get('mode', 'http')}"]
        if o.get("host"):
            parts.append(f"obfs-host={o['host']}")
    else:
        parts = ["v2ray-plugin", f"mode={o.get('mode', 'websocket')}"]
        if o.get("tls"):
            parts.append("tls")
        parts += [f"{k}={o[k]}" for k in ("host", "path") if o.get(k)]
    return ";".join(parts)
