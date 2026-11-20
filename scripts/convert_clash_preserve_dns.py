#!/usr/bin/env python3
"""Convert through the NWPU template, then restore source endpoints and DNS."""

import argparse
import copy
import os
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import urlencode, urlparse

import yaml


TEMPLATE = "https://raw.githubusercontent.com/dw2286/ACL4SSR/master/Clash/config/ACL4SSR_Online_Full_NWPU.ini"
EXCLUDE = r"免费|x0\.8|x0\.01|剩余流量|套餐到期|0\.1x|0\.01x"


def node_identity(node):
    return tuple(str(node.get(key, "")) for key in
                 ("type", "port", "cipher", "password", "uuid", "username"))


def restore_source(converted, source):
    for label, config in (("原订阅", source), ("转换结果", converted)):
        if not isinstance(config, dict) or not isinstance(config.get("proxies"), list) or not config["proxies"]:
            raise ValueError(f"{label}不是含有节点的 Clash YAML")
        if any(not isinstance(node, dict) or not isinstance(node.get("server"), str)
               for node in config["proxies"]):
            raise ValueError(f"{label}含有无效节点")
    if not isinstance(source.get("dns"), dict) or not source["dns"].get("enable"):
        raise ValueError("原订阅没有启用 DNS，无法恢复专用 DNS")

    endpoints = {}
    for node in source["proxies"]:
        identity = node_identity(node)
        endpoints.setdefault(identity, set()).add(node["server"])
    result = copy.deepcopy(converted)
    for node in result["proxies"]:
        identity = node_identity(node)
        if identity not in endpoints:
            raise ValueError("转换节点与原订阅不匹配；请重新下载同一份订阅后重试")
        if len(endpoints[identity]) != 1:
            raise ValueError("原订阅存在身份相同但域名不同的节点，不能安全匹配")
        node["server"] = next(iter(endpoints[identity]))

    source_dns = source["dns"]
    if result.get("dns") is not None and not isinstance(result["dns"], dict):
        raise ValueError("转换结果 DNS 格式无效")
    dns = result.setdefault("dns", {})
    dns["enable"] = True
    dns["use-hosts"] = source_dns.get("use-hosts", True)
    if source_dns.get("default-nameserver"):
        dns["default-nameserver"] = copy.deepcopy(source_dns["default-nameserver"])
    if not dns.get("nameserver"):
        dns["nameserver"] = copy.deepcopy(source_dns.get("nameserver", []))
    policies = source_dns.get("nameserver-policy", {})
    proxy_policies = source_dns.get("proxy-server-nameserver-policy", {})
    if not isinstance(policies, dict) or not isinstance(proxy_policies, dict):
        raise ValueError("原订阅 DNS 策略格式无效")
    dns["nameserver-policy"] = {**dns.get("nameserver-policy", {}), **copy.deepcopy(policies)}
    # Node DNS has its own policy when proxy-server-nameserver is configured.
    if dns.get("proxy-server-nameserver"):
        dns["proxy-server-nameserver-policy"] = {
            **dns.get("proxy-server-nameserver-policy", {}),
            **copy.deepcopy(policies), **copy.deepcopy(proxy_policies),
        }
    else:
        dns.pop("proxy-server-nameserver-policy", None)
    source_hosts = source.get("hosts", {})
    if not isinstance(source_hosts, dict) or not isinstance(result.get("hosts", {}), dict):
        raise ValueError("hosts 格式无效")
    if source_hosts or result.get("hosts"):
        result["hosts"] = {**result.get("hosts", {}), **copy.deepcopy(source_hosts)}
    return result


def load_yaml(location, proxy):
    if urlparse(location).scheme in ("http", "https"):
        command = ["curl", "--fail", "--silent", "--show-error", "--location", "--max-time", "60"]
        if proxy:
            command.extend(["--proxy", proxy])
        response = subprocess.run([*command, location], capture_output=True)
        if response.returncode:
            raise ValueError(f"下载失败（curl 退出码 {response.returncode}）")
        text = response.stdout.decode("utf-8-sig")
    else:
        text = Path(location).read_text(encoding="utf-8-sig")
    return yaml.safe_load(text)


def write_private_yaml(path, config):
    path = Path(path)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yaml.safe_dump(config, stream, allow_unicode=True, sort_keys=False)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="原始 Clash 订阅 URL 或 YAML 文件")
    parser.add_argument("--converted", help="已有转换 URL 或 YAML 文件；省略时使用肥羊增强型后端")
    parser.add_argument("--template", default=TEMPLATE, help="NWPU INI 的 raw URL")
    parser.add_argument("--exclude", default=EXCLUDE)
    parser.add_argument("--proxy", help="下载使用的 HTTP 代理；例如 http://127.0.0.1:7897")
    parser.add_argument("--output", required=True, help="修复后的 YAML 文件")
    args = parser.parse_args()
    phase = "参数检查"
    try:
        re.compile(args.exclude)
        phase = "原订阅读取"
        source = load_yaml(args.source, args.proxy)
        converted_location = args.converted
        if not converted_location:
            if urlparse(args.source).scheme not in ("http", "https"):
                raise ValueError("本地原订阅文件需要同时指定 --converted")
            converted_location = "https://url.v1.mk/sub?" + urlencode({
                "target": "clash", "url": args.source, "config": args.template,
                "exclude": args.exclude, "insert": "false", "emoji": "true",
                "list": "false", "xudp": "false", "udp": "false", "tfo": "false",
                "expand": "true", "scv": "false", "fdn": "false", "new_name": "true",
            })
        phase = "转换结果读取"
        converted = load_yaml(converted_location, args.proxy)
        phase = "源配置恢复"
        result = restore_source(converted, source)
        phase = "输出写入"
        # shortcut: rerun when the subscription changes; use a preserving backend for automatic updates.
        write_private_yaml(args.output, result)
    except Exception as error:
        # Download/parsing errors can contain credentials; report only the category.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        parser.exit(1, f"失败（{phase}）：{message}\n")
    print(f"已保存 {len(result['proxies'])} 个节点及共存 DNS：{args.output}")


if __name__ == "__main__":
    main()
