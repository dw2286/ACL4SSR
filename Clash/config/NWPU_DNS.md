# NWPU 模板与机场专用 DNS

普通订阅仍使用 `ACL4SSR_Online_Full_NWPU.ini`。在 `https://sub.cmliussss.net/` 选择“肥羊提供－增强型后端”，远程配置填写：

```text
https://raw.githubusercontent.com/dw2286/ACL4SSR/master/Clash/config/ACL4SSR_Online_Full_NWPU.ini
```

GitHub 的 `blob` 页面不是配置文件。旧转换链接若固定了历史提交 SHA，不会自动取得这里的更新。

## 原订阅可用，转换后失效

某些 Clash 订阅的节点域名需要机场提供的 `nameserver-policy` 和 `hosts`。转换结果可能丢失这些字段，甚至拿到与本机原订阅不同的节点 IP。勾选 `Clash.DoH` 不会继承原订阅 DNS，也不能恢复节点域名。只修改公共 INI 无法完整修复这两种情况。

本机修复脚本保留肥羊转换出的节点名称、分组、规则和过滤结果，用同一份原订阅恢复节点域名，并将机场 DNS 策略同时加入 `nameserver-policy` 与 `proxy-server-nameserver-policy`。网站继续使用 NWPU 的国内外 DNS 分流，节点使用机场的专用 DNS；原订阅的 DNS 引导地址和 hosts 也会保留。

需要 Python 3、PyYAML、curl，以及支持 `proxy-server-nameserver-policy` 的 Mihomo。脚本不会修改客户端正在使用的配置。

```bash
python3 scripts/convert_clash_preserve_dns.py \
  --source '你的原始 Clash 订阅 URL' \
  --output NWPU-fixed.yaml
```

如果下载需要本机代理，加上 `--proxy http://127.0.0.1:7897`。也可以处理已经下载的文件：

```bash
python3 scripts/convert_clash_preserve_dns.py \
  --source original.yaml --converted converted.yaml \
  --output NWPU-fixed.yaml
```

输出文件包含订阅凭据，权限为 `0600`。原订阅与转换结果的节点身份不一致或存在歧义时，脚本报错并保留已有输出。机场更新节点或 DNS 后，需要重新运行脚本；这是文件配置，不是能自动修复的在线订阅链接。
