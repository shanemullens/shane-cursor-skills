# Architecture Reference

Full, copy-pasteable Python code for building log generator scripts. All patterns are battle-tested across 5+ production generators and 30+ sourcetypes.

---

## Imports

Every generator script needs these:

```python
import argparse
import hashlib
import json
import os
import random
import string
import sys
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import requests
import urllib3
```

Dependencies: `requests>=2.31.0`, `urllib3>=2.0.0`

---

## HECConfig

```python
@dataclass
class HECConfig:
    url: str
    token: str
    index: str = "main"
    verify_ssl: bool = True
    batch_size: int = 50
    max_retries: int = 3
    source: str = "log:generator"
```

Always instantiate from environment variables:

```python
config = HECConfig(
    url=os.environ["SPLUNK_HEC_URL"],
    token=os.environ["SPLUNK_HEC_TOKEN"],
    index=os.environ.get("SPLUNK_INDEX", "main"),
    verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "true").lower() == "true",
)
```

---

## HECClient

Handles batched NDJSON POSTs with retry and backoff.

```python
class HECClient:
    ENDPOINT = "/services/collector/event"

    def __init__(self, config: HECConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Splunk {config.token}",
            "Content-Type": "application/json",
        })
        if not config.verify_ssl:
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def send_batch(self, events: list[dict]) -> bool:
        url = f"{self.config.url.rstrip('/')}{self.ENDPOINT}"
        payload = "\n".join(json.dumps(e) for e in events)
        for attempt in range(self.config.max_retries):
            try:
                resp = self.session.post(
                    url, data=payload,
                    verify=self.config.verify_ssl, timeout=30,
                )
                if resp.status_code == 200:
                    return True
                if resp.status_code == 429:
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
            except requests.RequestException:
                if attempt == self.config.max_retries - 1:
                    raise
                time.sleep(2 ** attempt)
        return False

    def send_all(self, events: list[dict]) -> int:
        sent = 0
        for i in range(0, len(events), self.config.batch_size):
            batch = events[i : i + self.config.batch_size]
            if self.send_batch(batch):
                sent += len(batch)
        return sent
```

Key details:
- `rstrip('/')` on the URL prevents double-path bugs when the user's URL already ends with `/`
- Payload is newline-delimited JSON (NDJSON), NOT a JSON array
- 429 (throttle) triggers exponential backoff; other errors retry up to `max_retries`
- Max payload per POST: ~1 MB. Keep `batch_size` at 50-100.

---

## BaseGenerator

Abstract base class with shared identity pools and utility methods.

```python
class BaseGenerator(ABC):
    SOURCETYPE: str = ""
    SOURCE: str = ""

    INTERNAL_IPS = [
        f"10.{random.randint(1, 50)}.{random.randint(1, 254)}.{random.randint(1, 254)}"
        for _ in range(30)
    ]
    EXTERNAL_IPS = (
        [f"198.51.100.{i}" for i in range(1, 21)]
        + [f"203.0.113.{i}" for i in range(1, 21)]
    )
    USERS = [
        f"{first}.{last}@company.com"
        for first, last in [
            ("john", "smith"), ("jane", "doe"), ("alice", "wong"), ("bob", "kumar"),
            ("carlos", "garcia"), ("diana", "chen"), ("erik", "johnson"), ("fatima", "ali"),
            ("george", "williams"), ("helen", "martinez"), ("ivan", "petrov"), ("julia", "kim"),
            ("kevin", "brown"), ("lisa", "taylor"), ("mike", "anderson"), ("nina", "patel"),
        ]
    ]
    HOSTNAMES = [
        f"{dept}-ws-{n:03d}"
        for dept in ("eng", "fin", "hr", "mkt", "ops")
        for n in range(1, 5)
    ]
    SERVERS = [
        f"{role}-{site}-{n:02d}"
        for role in ("web", "app", "db")
        for site in ("sjc", "rtp", "ldn")
        for n in (1, 2)
    ]
    FIREWALLS = [f"fw-{site}-{n:02d}" for site in ("sjc", "rtp", "ldn") for n in (1, 2)]

    CITIES = [
        ("San Jose", "California", "US", 37.3382, -121.8863),
        ("New York", "New York", "US", 40.7128, -74.0060),
        ("London", "England", "GB", 51.5074, -0.1278),
        ("Austin", "Texas", "US", 30.2672, -97.7431),
        ("Chicago", "Illinois", "US", 41.8781, -87.6298),
        ("Berlin", "Berlin", "DE", 52.5200, 13.4050),
        ("Tokyo", "Tokyo", "JP", 35.6762, 139.6503),
        ("Sydney", "NSW", "AU", -33.8688, 151.2093),
    ]

    def __init__(self, config: HECConfig):
        self.config = config

    # -- Timestamps --

    def _random_ts(self, start: datetime, end: datetime) -> float:
        """Random timestamp weighted ~70% toward business hours (08-18 UTC)."""
        delta = (end - start).total_seconds()
        offset = random.uniform(0, delta)
        dt = start + timedelta(seconds=offset)
        if 8 <= dt.hour <= 18:
            return dt.timestamp()
        if random.random() < 0.3:
            return dt.timestamp()
        return self._random_ts(start, end)

    def _iso(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    def _iso_ms(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%f"
        )[:-3] + "Z"

    def _iso_offset(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )

    # -- Identity helpers --

    def _sha256(self) -> str:
        return hashlib.sha256(uuid.uuid4().bytes).hexdigest()

    def _hex32(self) -> str:
        return self._sha256()[:32]

    def _uuid(self) -> str:
        return str(uuid.uuid4())

    def _uuid_short(self) -> str:
        return uuid.uuid4().hex[:8]

    # -- Selection helpers --

    def _weighted_choice(self, choices: list[tuple[Any, float]]) -> Any:
        """Pick from [(value, weight), ...] with weighted probability."""
        items, weights = zip(*choices)
        return random.choices(items, weights=weights, k=1)[0]

    def _score_category(self, score: int) -> str:
        if score >= 90:
            return "critical"
        if score >= 70:
            return "high"
        if score >= 40:
            return "medium"
        return "low"

    # -- HEC envelope --

    def _hec_wrap(
        self,
        event: dict,
        timestamp: float,
        sourcetype: str | None = None,
        host: str | None = None,
        index: str | None = None,
        source: str | None = None,
    ) -> dict:
        return {
            "time": round(timestamp, 3),
            "host": host or random.choice(self.HOSTNAMES),
            "source": source or self.SOURCE or self.SOURCETYPE,
            "sourcetype": sourcetype or self.SOURCETYPE,
            "index": index or self.config.index,
            "event": event,
        }

    @abstractmethod
    def generate(self, count: int, start: datetime, end: datetime) -> list[dict]:
        ...
```

Pool sizing rationale:
- 30 internal IPs, 40 external IPs -- enough variety without excessive uniqueness
- 16 users, 20 hostnames, 18 servers, 6 firewalls -- realistic for a mid-size org
- Class-level pools are shared across all generator instances for automatic correlation

---

## Catalog Mode CLI

For scripts that generate multiple sourcetypes selected via `--products`:

```python
PRODUCT_MAP: dict[str, type[BaseGenerator]] = {
    "my-source-a": MySourceAGenerator,
    "my-source-b": MySourceBGenerator,
}

def main():
    parser = argparse.ArgumentParser(description="Log Generator")
    parser.add_argument("--products", nargs="+", default=["all"],
                        help="Products to generate (or 'all')")
    parser.add_argument("--count", type=int, default=100,
                        help="Events per product")
    parser.add_argument("--hours", type=int, default=24,
                        help="Time range in hours from now")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print events to stdout instead of sending")
    args = parser.parse_args()

    config = HECConfig(
        url=os.environ["SPLUNK_HEC_URL"],
        token=os.environ["SPLUNK_HEC_TOKEN"],
        index=os.environ.get("SPLUNK_INDEX", "main"),
        verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "true").lower() == "true",
    )

    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=args.hours)
    products = PRODUCT_MAP if "all" in args.products else {
        k: v for k, v in PRODUCT_MAP.items() if k in args.products
    }

    client = HECClient(config)
    for name, gen_cls in products.items():
        gen = gen_cls(config)
        events = gen.generate(args.count, start, end)
        if args.dry_run:
            for e in events:
                print(json.dumps(e, indent=2))
        else:
            sent = client.send_all(events)
            print(f"Sent {sent} events for {name}")


if __name__ == "__main__":
    main()
```

---

## Scenario Mode CLI

For scripts that generate a time-sequenced narrative:

```python
def generate_scenario(config: HECConfig, start: datetime, end: datetime) -> list[dict]:
    """Build a time-ordered event list across multiple sourcetypes."""
    events: list[dict] = []
    duration = (end - start).total_seconds()

    attacker_ip = "203.0.113.99"
    target_user = "john.smith@company.com"
    c2_domain = "evil.example.com"

    # Phase 1: Initial access (0-10% of timeline)
    t = start + timedelta(seconds=duration * 0.05)
    events.append({
        "time": round(t.timestamp(), 3),
        "host": "fw-sjc-01",
        "source": "vendor:firewall:connection",
        "sourcetype": "vendor:firewall:connection",
        "index": config.index,
        "event": {
            "action": "allowed",
            "src_ip": attacker_ip,
            "dst_ip": "10.1.2.50",
            "dst_port": 443,
            "user": target_user,
        },
    })

    # Phase 2: Lateral movement (20-40% of timeline)
    # ... add events for each phase ...

    # Phase N: Exfiltration
    # ... final phase events ...

    events.sort(key=lambda e: e["time"])
    return events


def main():
    parser = argparse.ArgumentParser(description="Attack Scenario Generator")
    parser.add_argument("--hours", type=int, default=24,
                        help="Scenario duration in hours from now")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print events to stdout instead of sending")
    args = parser.parse_args()

    config = HECConfig(
        url=os.environ.get("SPLUNK_HEC_URL", ""),
        token=os.environ.get("SPLUNK_HEC_TOKEN", ""),
        index=os.environ.get("SPLUNK_INDEX", "main"),
        verify_ssl=os.environ.get("SPLUNK_VERIFY_SSL", "true").lower() == "true",
    )

    end = datetime.now(tz=timezone.utc)
    start = end - timedelta(hours=args.hours)
    events = generate_scenario(config, start, end)

    if args.dry_run:
        for e in events:
            print(json.dumps(e, indent=2))
        print(f"\n--- {len(events)} events (dry run) ---")
    else:
        if not config.url or not config.token:
            print("Set SPLUNK_HEC_URL and SPLUNK_HEC_TOKEN", file=sys.stderr)
            sys.exit(1)
        client = HECClient(config)
        sent = client.send_all(events)
        print(f"Sent {sent}/{len(events)} events")


if __name__ == "__main__":
    main()
```

Scenario design tips:
- Define shared IOCs at the top (`attacker_ip`, `target_user`, `malware_hash`, `c2_domain`)
- Place events at percentage offsets of the total timeline for reproducible spacing
- Add 5-10 background noise events per phase to make the scenario realistic
- Always `events.sort(key=lambda e: e["time"])` before sending

---

## Example: Minimal Custom Generator (Catalog Mode)

A complete generator for a hypothetical `vendor:firewall:connection` sourcetype:

```python
class FirewallConnectionGenerator(BaseGenerator):
    SOURCETYPE = "vendor:firewall:connection"
    SOURCE = "vendor:firewall:connection"

    ACTIONS = [("allowed", 0.75), ("blocked", 0.15), ("dropped", 0.10)]
    PROTOCOLS = ["TCP", "UDP", "ICMP"]
    PORTS = [22, 53, 80, 443, 445, 3389, 8080, 8443]

    def generate(self, count: int, start: datetime, end: datetime) -> list[dict]:
        events = []
        for _ in range(count):
            ts = self._random_ts(start, end)
            action = self._weighted_choice(self.ACTIONS)
            event = {
                "action": action,
                "protocol": random.choice(self.PROTOCOLS),
                "src_ip": random.choice(self.INTERNAL_IPS),
                "dst_ip": random.choice(self.EXTERNAL_IPS),
                "src_port": random.randint(1024, 65535),
                "dst_port": random.choice(self.PORTS),
                "bytes_in": random.randint(100, 50000),
                "bytes_out": random.randint(100, 50000),
                "duration": round(random.uniform(0.01, 300.0), 3),
                "device": random.choice(self.FIREWALLS),
                "timestamp": self._iso(ts),
            }
            events.append(self._hec_wrap(event, ts, host=event["device"]))
        return events
```

---

## Example: Extending from Another Generator

When a base script already exists (e.g., `cisco_log_generator.py` provides `BaseGenerator`, `HECClient`, `HECConfig`), import and extend:

```python
from cisco_log_generator import BaseGenerator, HECClient, HECConfig

class MyNewSourceGenerator(BaseGenerator):
    SOURCETYPE = "myvendor:myproduct:event"
    SOURCE = "myvendor:myproduct:event"

    def generate(self, count, start, end):
        events = []
        for _ in range(count):
            ts = self._random_ts(start, end)
            event = {"status": "ok", "user": random.choice(self.USERS)}
            events.append(self._hec_wrap(event, ts))
        return events
```

This pattern was used for `mulesoft_aws_log_generator.py` and `cisco_enterprise_networking_log_generator.py`, which import the shared infrastructure from `cisco_log_generator.py`.

---

## Domain-Specific Data Pools

For generators with rich domain context (trading partners, cloud resources, etc.), define frozen dataclasses:

```python
@dataclass(frozen=True)
class TradingPartner:
    name: str
    partner_id: str
    protocol: str
    external_ip: str

TRADING_PARTNERS = [
    TradingPartner("Acme Distribution", "ACME-001", "AS2", "198.51.100.10"),
    TradingPartner("GlobalParts Inc", "GPARTS-002", "SFTP", "198.51.100.20"),
]
```

This keeps domain data structured and type-safe while enabling cross-generator correlation (e.g., `PARTNER_IPS = [p.external_ip for p in TRADING_PARTNERS]`).

---

## Environment Variable Setup

### Linux/macOS (bash)
```bash
export SPLUNK_HEC_URL="https://inputs.splunkcloud.com:8088"
export SPLUNK_HEC_TOKEN="your-hec-token"
export SPLUNK_INDEX="main"
```

### Windows (PowerShell)
```powershell
$env:SPLUNK_HEC_URL = "https://inputs.splunkcloud.com:8088"
$env:SPLUNK_HEC_TOKEN = "your-hec-token"
$env:SPLUNK_INDEX = "main"
```

### Windows (cmd)
```cmd
set SPLUNK_HEC_URL=https://inputs.splunkcloud.com:8088
set SPLUNK_HEC_TOKEN=your-hec-token
set SPLUNK_INDEX=main
```
