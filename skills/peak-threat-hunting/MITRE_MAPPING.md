# MITRE ATT&CK Hunting Guidance

Map hunts to ATT&CK techniques for coverage tracking and structured hunting.

---

## Using ATT&CK for Hunt Planning

1. **Identify priority techniques** based on threat intelligence
2. **Check existing detection coverage** 
3. **Design hunts** targeting coverage gaps
4. **Track techniques hunted** for metrics

---

## High-Priority Techniques by Tactic

### Initial Access (TA0001)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Phishing | T1566 | Email logs, URL reputation, attachment analysis | Email gateway, proxy |
| External Remote Services | T1133 | VPN/RDP login analysis, geo anomalies | Auth logs, VPN |
| Valid Accounts | T1078 | Account usage patterns, impossible travel | Auth logs |

**Sample Hunt - Suspicious VPN Logins**:
```spl
index=<vpn_index>
| stats count dc(src_ip) as unique_ips by user
| iplocation src_ip
| where unique_ips > 3
| sort -unique_ips
```

### Execution (TA0002)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Command/Scripting Interpreter | T1059 | Suspicious cmdline, encoded commands | Endpoint logs |
| Scheduled Task/Job | T1053 | New scheduled tasks, unusual timing | Task scheduler logs |
| Windows Management Instrumentation | T1047 | WMI process creation, lateral movement | WMI logs, Sysmon |

**Sample Hunt - Encoded PowerShell**:
```spl
index=<endpoint_index> process_name=powershell.exe
| where match(cmdline, "(?i)(-enc|-encodedcommand|frombase64)")
| stats count by host, user, cmdline
| sort -count
```

### Persistence (TA0003)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Registry Run Keys | T1547.001 | New/modified run keys | Sysmon, registry |
| Scheduled Task | T1053.005 | New tasks, unusual execution times | Task logs |
| Create Account | T1136 | New account creation, unusual timing | Security event logs |

**Sample Hunt - New Scheduled Tasks**:
```spl
index=<endpoint_index> EventCode=4698
| stats earliest(_time) as created by TaskName, host
| where created > relative_time(now(), "-7d")
| sort created
```

### Privilege Escalation (TA0004)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Valid Accounts: Domain Admin | T1078.002 | DA account usage patterns | Auth logs, DC logs |
| Access Token Manipulation | T1134 | Token impersonation indicators | Endpoint logs |
| Exploitation for Privilege Escalation | T1068 | Crash/exploit indicators | Endpoint, AV logs |

**Sample Hunt - Domain Admin Usage**:
```spl
index=<auth_index> user IN ("*admin*", "*DA_*")
| stats count dc(dest) as unique_targets earliest(_time) as first latest(_time) as last by user, src_ip
| sort -unique_targets
```

### Defense Evasion (TA0005)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Masquerading | T1036 | Process name anomalies, path analysis | Endpoint logs |
| Obfuscated Files | T1027 | Encoded content, entropy analysis | Endpoint, email |
| Indicator Removal | T1070 | Log clearing, timestamp modification | Security logs |

**Sample Hunt - Log Clearing**:
```spl
index=<windows_index> EventCode IN (1102, 104)
| stats count by host, user
| sort -count
```

### Credential Access (TA0006)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Brute Force | T1110 | Failed login patterns, password spray | Auth logs |
| OS Credential Dumping | T1003 | LSASS access, mimikatz indicators | Endpoint logs, Sysmon |
| Credentials from Password Stores | T1555 | Browser/vault access | Endpoint logs |

**Sample Hunt - LSASS Access**:
```spl
index=<sysmon_index> EventCode=10 TargetImage="*lsass.exe"
| where NOT match(SourceImage, "(MsMpEng|csrss|services)\.exe$")
| stats count by SourceImage, host
| sort -count
```

### Discovery (TA0007)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Network Service Discovery | T1046 | Port scanning patterns | Network logs, firewall |
| System Information Discovery | T1082 | Recon commands (systeminfo, etc.) | Endpoint logs |
| Account Discovery | T1087 | AD enumeration, net commands | Endpoint, DC logs |

**Sample Hunt - Network Scanning**:
```spl
index=<firewall_index>
| stats dc(dest_port) as ports_scanned dc(dest_ip) as ips_scanned by src_ip
| where ports_scanned > 100 OR ips_scanned > 50
| sort -ports_scanned
```

### Lateral Movement (TA0008)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Remote Services: RDP | T1021.001 | Unusual RDP connections | Network, auth logs |
| Remote Services: SMB | T1021.002 | SMB admin share access | Network, endpoint |
| Remote Services: WinRM | T1021.006 | WinRM connections | Endpoint logs |

**Sample Hunt - Lateral RDP**:
```spl
index=<auth_index> EventCode=4624 LogonType=10
| stats count dc(dest) as unique_dests by user, src_ip
| where unique_dests > 3
| sort -unique_dests
```

### Collection (TA0009)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Data Staged | T1074 | Large file creation, archive creation | Endpoint logs |
| Email Collection | T1114 | Bulk email access, forwarding rules | Email logs, O365 |
| Screen Capture | T1113 | Screenshot tool execution | Endpoint logs |

**Sample Hunt - Data Staging**:
```spl
index=<endpoint_index> (file_extension IN ("zip", "7z", "rar") OR process IN ("7z.exe", "winrar.exe"))
| stats count sum(file_size) as total_size by user, host, file_path
| where total_size > 100000000
| sort -total_size
```

### Command and Control (TA0011)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Application Layer Protocol: DNS | T1071.004 | DNS tunneling, long queries | DNS logs |
| Application Layer Protocol: Web | T1071.001 | Beaconing, encoded payloads | Proxy logs |
| Ingress Tool Transfer | T1105 | Download from rare domains | Proxy, endpoint |

**Sample Hunt - DNS Tunneling**:
```spl
index=<dns_index>
| eval query_len = len(query)
| where query_len > 50
| rex field=query "\.(?<domain>[^.]+\.[^.]+)$"
| stats count max(query_len) as max_len by src_ip, domain
| where count > 100 AND max_len > 60
| sort -max_len
```

**Sample Hunt - HTTP Beaconing**:
```spl
index=<proxy_index>
| bin _time span=5m
| stats count by src_ip, dest, _time
| eventstats stdev(count) as count_stdev avg(count) as count_avg by src_ip, dest
| where count_stdev < (count_avg * 0.2) AND count > 10
| stats count by src_ip, dest
| sort -count
```

### Exfiltration (TA0010)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Exfiltration Over C2 Channel | T1041 | Large outbound transfers | Proxy, firewall |
| Exfiltration Over Web Service | T1567 | Cloud storage uploads | Proxy, CASB |
| Exfiltration Over Alternative Protocol | T1048 | DNS/ICMP exfil, unusual protocols | Network logs |

**Sample Hunt - Large Outbound Transfers**:
```spl
index=<firewall_index> direction=outbound
| stats sum(bytes_out) as total_bytes by src_ip, dest_ip
| where total_bytes > 500000000
| sort -total_bytes
```

### Impact (TA0040)

| Technique | ID | Hunt Approach | Key Data Sources |
|-----------|-----|--------------|-----------------|
| Data Encrypted for Impact | T1486 | Ransomware indicators, mass file ops | Endpoint logs |
| System Shutdown/Reboot | T1529 | Unexpected shutdowns | System logs |
| Inhibit System Recovery | T1490 | VSS deletion, backup tampering | Endpoint logs |

**Sample Hunt - Shadow Copy Deletion**:
```spl
index=<endpoint_index>
| where match(cmdline, "(?i)(vssadmin|wmic).*delete.*shadow")
| table _time, host, user, process, cmdline
```

---

## Coverage Tracking

### Query Existing Technique Coverage
```spl
index=<es_notable_index>
| stats dc(rule_name) as rules count by mitre_attack_technique_id
| sort mitre_attack_technique_id
```

### Gap Analysis Template
```markdown
| Tactic | Technique | ID | Current Coverage | Hunt Priority |
|--------|-----------|-----|------------------|---------------|
| [Tactic] | [Technique] | T#### | None/Partial/Full | High/Medium/Low |
```

### Coverage Heatmap Query
```spl
| inputlookup mitre_attack_lookup
| join type=left technique_id 
    [search index=<es_notable_index> | stats count by mitre_attack_technique_id as technique_id]
| eval coverage=if(isnull(count), "none", if(count>10, "high", "low"))
| table tactic, technique, technique_id, coverage
```

---

## Mapping Hunt Findings to ATT&CK

When documenting hunt findings, include:

1. **Primary technique(s)**: What ATT&CK technique did you detect?
2. **Sub-techniques**: Be specific (e.g., T1059.001 for PowerShell, not just T1059)
3. **Data source used**: Map to ATT&CK data sources
4. **Detection method**: How you found it

Example:
```markdown
Finding: Encoded PowerShell execution
- Technique: T1059.001 (Command and Scripting Interpreter: PowerShell)
- Data Source: Process (Sysmon EventCode 1)
- Detection: Stack counting on cmdline containing '-enc' or 'frombase64'
```
