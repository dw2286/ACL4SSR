import copy
import importlib.util
from pathlib import Path
import stat
import tempfile
import unittest

import yaml


SCRIPT = Path(__file__).resolve().parents[1] / "convert_clash_preserve_dns.py"
SPEC = importlib.util.spec_from_file_location("convert_clash_preserve_dns", SCRIPT)
CONVERTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONVERTER)


class PreserveDnsTests(unittest.TestCase):
    def setUp(self):
        self.source = {
            "proxies": [{"name": "香港", "type": "ss", "server": "hk.airport.invalid",
                         "port": 443, "cipher": "aes-128-gcm", "password": "test-only"}],
            "dns": {"enable": True, "use-hosts": True,
                    "default-nameserver": ["223.5.5.5"],
                    "nameserver": ["119.29.29.29"],
                    "nameserver-policy": {"+.airport.invalid": ["tcp://dns.airport.invalid:8080"]}},
            "hosts": {"dns.airport.invalid": "192.0.2.53"},
        }
        self.converted = {
            "proxies": [{**self.source["proxies"][0], "name": "🇭🇰 香港", "server": "192.0.2.1"}],
            "proxy-groups": [{"name": "选择", "type": "select", "proxies": ["🇭🇰 香港"]}],
            "rules": ["MATCH,选择"],
            "dns": {"nameserver": ["https://dns.google/dns-query#选择"],
                    "proxy-server-nameserver": ["https://doh.360.cn/dns-query#DIRECT"],
                    "nameserver-policy": {"geosite:cn": ["https://doh.360.cn/dns-query#DIRECT"]}},
            "hosts": {"other.invalid": "192.0.2.54"},
        }

    def test_restore_endpoints_and_both_dns_policies_without_changing_routing(self):
        before = copy.deepcopy(self.converted)
        result = CONVERTER.restore_source(self.converted, self.source)
        self.assertEqual(result["proxies"][0]["server"], "hk.airport.invalid")
        for key in ("proxy-groups", "rules"):
            self.assertEqual(result[key], before[key])
        self.assertEqual(result["proxies"][0]["name"], before["proxies"][0]["name"])
        self.assertEqual(result["dns"]["nameserver"], before["dns"]["nameserver"])
        for key in ("nameserver-policy", "proxy-server-nameserver-policy"):
            self.assertEqual(result["dns"][key]["+.airport.invalid"], ["tcp://dns.airport.invalid:8080"])
        self.assertIn("geosite:cn", result["dns"]["nameserver-policy"])
        self.assertEqual(result["hosts"], {**before["hosts"], **self.source["hosts"]})
        self.assertEqual(self.converted, before)

    def test_unknown_and_ambiguous_nodes_are_rejected(self):
        self.converted["proxies"][0]["password"] = "different"
        with self.assertRaises(ValueError):
            CONVERTER.restore_source(self.converted, self.source)
        self.converted["proxies"][0]["password"] = "test-only"
        self.source["proxies"].append({**self.source["proxies"][0], "server": "different.airport.invalid"})
        with self.assertRaisesRegex(ValueError, "身份相同"):
            CONVERTER.restore_source(self.converted, self.source)

    def test_missing_or_invalid_configuration_is_rejected(self):
        for invalid in ("No nodes were found!", {}, {"proxies": []}, {"proxies": [None]}):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                CONVERTER.restore_source(invalid, self.source)
        self.source.pop("dns")
        with self.assertRaisesRegex(ValueError, "没有启用 DNS"):
            CONVERTER.restore_source(self.converted, self.source)

    def test_ambiguity_in_filtered_out_nodes_does_not_block_conversion(self):
        unused = {**self.source["proxies"][0], "password": "unused"}
        self.source["proxies"].extend([unused, {**unused, "server": "another.airport.invalid"}])
        self.assertEqual(CONVERTER.restore_source(self.converted, self.source)["proxies"][0]["server"],
                         "hk.airport.invalid")

    def test_without_separate_node_resolver_nameserver_policy_is_used(self):
        self.converted["dns"].pop("proxy-server-nameserver")
        result = CONVERTER.restore_source(self.converted, self.source)
        self.assertNotIn("proxy-server-nameserver-policy", result["dns"])
        self.assertIn("+.airport.invalid", result["dns"]["nameserver-policy"])

    def test_output_replaces_existing_file_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fixed.yaml"
            path.write_text("old", encoding="utf-8")
            result = CONVERTER.restore_source(self.converted, self.source)
            CONVERTER.write_private_yaml(path, result)
            self.assertEqual(yaml.safe_load(path.read_text(encoding="utf-8")), result)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(list(Path(directory).iterdir()), [path])


if __name__ == "__main__":
    unittest.main()
