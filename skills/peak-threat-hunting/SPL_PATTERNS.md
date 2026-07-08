# Common Hunting SPL Patterns

Reusable SPL patterns for threat hunting analysis.

---

## Data Exploration

### Assess Data Volume and Coverage
```spl
| tstats count WHERE index=* by index, sourcetype 
| sort -count
```

### Field Summary for a Sourcetype
```spl
index=<index> sourcetype=<sourcetype> 
| head 10000 
| fieldsummary 
| table field, count, distinct_count, is_exact, numeric_count, values
| sort -count
```

### Timestamp Range Check
```spl
index=<index> 
| stats min(_time) as earliest max(_time) as latest 
| eval earliest=strftime(earliest, "%Y-%m-%d %H:%M:%S")
| eval latest=strftime(latest, "%Y-%m-%d %H:%M:%S")
```

### Event Sample
```spl
index=<index> sourcetype=<sourcetype>
| head 10
| table _time, _raw
```

---

## Stack Counting (Least Frequency of Occurrence)

Core hunting technique: rare values often indicate anomalies.

### Basic LFO - Single Field
```spl
index=<index>
| stats count by <field>
| sort count
| head 20
```

### LFO with Context
```spl
index=<index>
| stats count values(src_ip) as sources dc(src_ip) as source_count by <field>
| sort count
| where count < 10
```

### Multi-field LFO
```spl
index=<index>
| stats count by <field1>, <field2>
| sort count
| head 50
```

### LFO with Time Context
```spl
index=<index>
| stats count earliest(_time) as first_seen latest(_time) as last_seen by <field>
| eval first_seen=strftime(first_seen, "%Y-%m-%d %H:%M")
| eval last_seen=strftime(last_seen, "%Y-%m-%d %H:%M")
| sort count
```

---

## Statistical Outlier Detection

### Z-Score Outliers (Numeric Fields)
```spl
index=<index>
| stats count as event_count by <grouping_field>
| eventstats avg(event_count) as avg_count stdev(event_count) as stdev_count
| eval z_score = round((event_count - avg_count) / stdev_count, 2)
| where z_score > 3 OR z_score < -3
| sort -z_score
```

### Interquartile Range (IQR) Outliers
```spl
index=<index>
| stats count as event_count by <grouping_field>
| eventstats perc25(event_count) as q1 perc75(event_count) as q3
| eval iqr = q3 - q1
| eval lower_bound = q1 - (1.5 * iqr)
| eval upper_bound = q3 + (1.5 * iqr)
| where event_count < lower_bound OR event_count > upper_bound
```

### Time-Based Anomalies (Hour of Day)
```spl
index=<index>
| eval hour = strftime(_time, "%H")
| stats count by user, hour
| eventstats avg(count) as avg_count stdev(count) as stdev_count by user
| eval z_score = (count - avg_count) / stdev_count
| where z_score > 2
| sort -z_score
```

---

## Temporal Analysis

### Activity Timeline
```spl
index=<index>
| timechart span=1h count by <field>
```

### First/Last Seen Analysis
```spl
index=<index>
| stats earliest(_time) as first_seen latest(_time) as last_seen count by <field>
| eval first_seen = strftime(first_seen, "%Y-%m-%d %H:%M")
| eval last_seen = strftime(last_seen, "%Y-%m-%d %H:%M")
| eval duration_days = round((latest_seen - earliest_seen) / 86400, 1)
| sort first_seen
```

### New Values Detection
```spl
index=<index> earliest=-7d latest=now
| stats earliest(_time) as first_seen by <field>
| where first_seen > relative_time(now(), "-24h")
| eval first_seen = strftime(first_seen, "%Y-%m-%d %H:%M")
| sort first_seen
```

### Baseline Deviation
```spl
index=<index> earliest=-30d
| timechart span=1d count as daily_count
| predict daily_count future_timespan=0 
| eval deviation = daily_count - predicted(daily_count)
| where abs(deviation) > 2 * stdev(daily_count)
```

---

## Behavioral Analysis

### User Baseline Deviation
```spl
index=<index>
| stats count as today_count by user
| join type=left user 
    [search index=<index> earliest=-30d latest=-1d
    | stats avg(count) as baseline_avg stdev(count) as baseline_stdev by user]
| eval z_score = (today_count - baseline_avg) / baseline_stdev
| where z_score > 3
```

### Process Ancestry Chain
```spl
index=<index> sourcetype=<endpoint_sourcetype>
| table _time, host, parent_process, process, user, cmdline
| sort _time
```

### Network Connection Beaconing
```spl
index=<index> sourcetype=<network_sourcetype>
| stats count avg(bytes_out) as avg_bytes stdev(bytes_out) as stdev_bytes by src_ip, dest_ip, dest_port
| where count > 100 AND stdev_bytes / avg_bytes < 0.1
| sort -count
```

---

## Clustering and Grouping

### Text Clustering
```spl
index=<index>
| cluster field=<text_field> showcount=true
| sort -cluster_count
| dedup cluster_label
| table cluster_label, cluster_count
```

### Event Correlation
```spl
index=<index>
| transaction <grouping_field> maxspan=5m
| stats count duration by eventcount
| sort -count
```

### Session Analysis
```spl
index=<index>
| transaction user host maxspan=30m maxpause=5m
| stats count avg(duration) as avg_session_sec dc(host) as hosts_accessed by user
| sort -hosts_accessed
```

---

## Network Hunting

### DNS Query Analysis (Tunneling Detection)
```spl
index=<dns_index>
| eval query_length = len(query)
| stats count avg(query_length) as avg_len max(query_length) as max_len by src_ip, query_type
| where max_len > 50 OR count > 1000
| sort -max_len
```

### Long Subdomain Detection
```spl
index=<dns_index>
| rex field=query "^(?<subdomain>[^.]+)\."
| eval subdomain_len = len(subdomain)
| where subdomain_len > 30
| stats count by subdomain, query, src_ip
| sort -subdomain_len
```

### Unusual Port Activity
```spl
index=<firewall_index>
| stats dc(src_ip) as unique_sources count by dest_port
| where unique_sources < 5 AND count > 100
| sort -count
```

### Outbound Connection Analysis
```spl
index=<firewall_index> action=allowed direction=outbound
| stats sum(bytes_out) as total_bytes dc(dest_ip) as unique_dests count by src_ip
| sort -total_bytes
```

---

## Endpoint Hunting

### Suspicious Process Names
```spl
index=<endpoint_index>
| rex field=process_name "(?<name_no_ext>.*)\.[^.]+$"
| stats count by process_name, name_no_ext
| where match(name_no_ext, "^(cmd|powershell|wscript|cscript|mshta|regsvr32)$")
```

### Command Line Analysis - Base64
```spl
index=<endpoint_index>
| where match(cmdline, "(?i)(base64|encodedcommand|-enc|-e )")
| table _time, host, user, process, cmdline
```

### Unsigned/Unusual Binaries
```spl
index=<endpoint_index>
| where isnull(signature) OR signature_status!="valid"
| stats count by process_path, signature_status
| sort -count
```

### Lateral Movement Indicators
```spl
index=<endpoint_index> (EventCode=4624 OR EventCode=4648)
| stats count dc(dest) as unique_targets by src_user, src_ip
| where unique_targets > 5
| sort -unique_targets
```

---

## Authentication Hunting

### Failed Login Patterns
```spl
index=<auth_index> action=failure
| stats count dc(dest) as targets by user, src_ip
| where count > 10
| sort -count
```

### Password Spray Detection
```spl
index=<auth_index> action=failure
| bin _time span=5m
| stats dc(user) as unique_users count by src_ip, _time
| where unique_users > 10
| sort -unique_users
```

### Impossible Travel
```spl
index=<auth_index> action=success
| sort user, _time
| streamstats current=f last(src_ip) as prev_ip last(_time) as prev_time by user
| where src_ip != prev_ip
| eval time_diff_min = (_time - prev_time) / 60
| iplocation src_ip
| iplocation prefix=prev_ prev_ip
| where time_diff_min < 60 AND City != prev_City
```

---

## Model-Assisted Hunting

### Built-in Anomaly Detection
```spl
index=<index>
| timechart span=1h count
| anomalydetection count action=annotate
| where isanomalous=1
```

### Density-Based Outliers
```spl
index=<index>
| stats count by <field1>, <field2>
| anomalydetection <field1> <field2> action=annotate
| where isanomalous=1
```

### Time Series Prediction
```spl
index=<index>
| timechart span=1h count
| predict count future_timespan=24 holdback=24
| eval deviation = count - predicted(count)
| where deviation > 2 * stdev(count)
```

---

## Detection Conversion

### Save as Alert (template)
```spl
index=<index> 
[hunting query logic]
| where [threshold condition]
| table _time, [key fields for investigation]
```

### Add Notable Event Fields (ES)
```spl
index=<index>
[hunting query logic]
| eval rule_name="[Detection Name]"
| eval rule_description="[What this detects]"
| eval severity="[critical|high|medium|low]"
| eval mitre_attack="[T####]"
```
