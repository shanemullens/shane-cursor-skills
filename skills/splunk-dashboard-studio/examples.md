# Dashboard Definition Examples

Complete, production-ready dashboard definitions demonstrating key patterns.

## Example 1: Security Operations Overview (Grid Layout)

A SOC dashboard with KPI single values, time-series chart, and detail table. Demonstrates: base+chain searches, tokens, inputs, conditional formatting, and drilldown.

```json
{
  "title": "Security Operations Overview",
  "description": "Real-time security event monitoring with interactive drill-down",
  "inputs": {
    "input_time": {
      "type": "input.timerange",
      "title": "Time Range",
      "options": {
        "token": "global_time",
        "defaultValue": "-24h@h,now"
      }
    },
    "input_severity": {
      "type": "input.dropdown",
      "title": "Severity",
      "options": {
        "token": "sev_filter",
        "defaultValue": "*",
        "items": [
          { "label": "All Severities", "value": "*" },
          { "label": "Critical", "value": "critical" },
          { "label": "High", "value": "high" },
          { "label": "Medium", "value": "medium" },
          { "label": "Low", "value": "low" }
        ]
      }
    }
  },
  "defaults": {
    "dataSources": {
      "ds.search": {
        "options": {
          "queryParameters": {
            "earliest": "$global_time.earliest$",
            "latest": "$global_time.latest$"
          }
        }
      }
    }
  },
  "dataSources": {
    "ds_base": {
      "type": "ds.search",
      "options": {
        "query": "index=security sourcetype=syslog severity=$sev_filter|s$\n| eval severity=lower(severity)\n| stats count by _time, severity, src_ip, dest_ip, action",
        "queryParameters": {
          "earliest": "$global_time.earliest$",
          "latest": "$global_time.latest$"
        }
      },
      "name": "Base Security Events"
    },
    "ds_total_events": {
      "type": "ds.chain",
      "options": {
        "query": "| stats count as total_events",
        "extend": "ds_base"
      },
      "name": "Total Events"
    },
    "ds_critical_count": {
      "type": "ds.chain",
      "options": {
        "query": "| search severity=critical | stats count as critical_count",
        "extend": "ds_base"
      },
      "name": "Critical Count"
    },
    "ds_timeline": {
      "type": "ds.chain",
      "options": {
        "query": "| timechart count by severity",
        "extend": "ds_base"
      },
      "name": "Event Timeline"
    },
    "ds_top_sources": {
      "type": "ds.chain",
      "options": {
        "query": "| stats count by src_ip, severity | sort -count | head 20",
        "extend": "ds_base"
      },
      "name": "Top Sources"
    }
  },
  "visualizations": {
    "viz_total": {
      "type": "splunk.singlevalue",
      "title": "Total Events",
      "dataSources": { "primary": "ds_total_events" },
      "options": {
        "majorFontSize": 48,
        "backgroundColor": "transparent",
        "underLabel": "Events"
      }
    },
    "viz_critical": {
      "type": "splunk.singlevalue",
      "title": "Critical Alerts",
      "dataSources": { "primary": "ds_critical_count" },
      "options": {
        "majorFontSize": 48,
        "majorColor": "#DC4E41",
        "backgroundColor": "transparent",
        "underLabel": "Critical"
      }
    },
    "viz_timeline": {
      "type": "splunk.area",
      "title": "Event Timeline by Severity",
      "dataSources": { "primary": "ds_timeline" },
      "options": {
        "stackMode": "stacked",
        "seriesColorsByField": {
          "critical": "#DC4E41",
          "high": "#F8BE34",
          "medium": "#F1813F",
          "low": "#53A051",
          "info": "#0076D3"
        },
        "legendDisplay": "bottom",
        "areaOpacity": 0.7,
        "showLines": true,
        "yAxisTitleText": "Event Count"
      }
    },
    "viz_top_sources": {
      "type": "splunk.table",
      "title": "Top Source IPs",
      "dataSources": { "primary": "ds_top_sources" },
      "options": {
        "count": 10,
        "drilldown": "row",
        "columnFormat": {
          "severity": {
            "rowBackgroundColors": "> table | seriesByName(\"severity\") | matchValue(sevColorConfig)"
          },
          "count": {
            "data": "> table | seriesByName(\"count\") | formatByType(countFormat)"
          }
        }
      },
      "context": {
        "sevColorConfig": [
          { "match": "critical", "value": "#DC4E41" },
          { "match": "high", "value": "#F8BE34" },
          { "match": "medium", "value": "#F1813F" },
          { "match": "low", "value": "#53A051" }
        ],
        "countFormat": {
          "number": { "thousandSeparated": true, "precision": 0 }
        }
      },
      "eventHandlers": [
        {
          "type": "drilldown.setToken",
          "options": {
            "tokens": [
              { "token": "selected_ip", "key": "row.src_ip.value" }
            ]
          }
        }
      ]
    }
  },
  "layout": {
    "globalInputs": ["input_time", "input_severity"],
    "tabs": {
      "items": [{ "layoutId": "layout_1", "label": "Overview" }]
    },
    "layoutDefinitions": {
      "layout_1": {
        "type": "grid",
        "options": { "width": 1440 },
        "structure": [
          { "item": "viz_total", "type": "block", "position": { "x": 0, "y": 0, "w": 720, "h": 150 } },
          { "item": "viz_critical", "type": "block", "position": { "x": 720, "y": 0, "w": 720, "h": 150 } },
          { "item": "viz_timeline", "type": "block", "position": { "x": 0, "y": 150, "w": 1440, "h": 400 } },
          { "item": "viz_top_sources", "type": "block", "position": { "x": 0, "y": 550, "w": 1440, "h": 400 } }
        ]
      }
    }
  },
  "expressions": {},
  "applicationProperties": {}
}
```

---

## Example 2: Executive KPI Dashboard (Absolute Layout)

A branded executive dashboard with background panels, shaped sections, and polished styling. Demonstrates: absolute layout, shapes as backgrounds, markdown headers, single values with sparklines, and custom theming.

```json
{
  "title": "Executive KPI Dashboard",
  "description": "High-level business metrics with trend indicators",
  "inputs": {
    "input_time": {
      "type": "input.timerange",
      "title": "Time Range",
      "options": {
        "token": "global_time",
        "defaultValue": "-7d@d,now"
      }
    }
  },
  "defaults": {
    "dataSources": {
      "ds.search": {
        "options": {
          "queryParameters": {
            "earliest": "$global_time.earliest$",
            "latest": "$global_time.latest$"
          }
        }
      }
    }
  },
  "dataSources": {
    "ds_revenue": {
      "type": "ds.search",
      "options": {
        "query": "index=business sourcetype=transactions | timechart sum(amount) as revenue"
      },
      "name": "Revenue Trend"
    },
    "ds_users": {
      "type": "ds.search",
      "options": {
        "query": "index=web sourcetype=access_combined | timechart dc(clientip) as active_users"
      },
      "name": "Active Users"
    },
    "ds_errors": {
      "type": "ds.search",
      "options": {
        "query": "index=web sourcetype=access_combined status>=500 | timechart count as errors"
      },
      "name": "Error Count"
    }
  },
  "visualizations": {
    "viz_bg_header": {
      "type": "splunk.rectangle",
      "options": {
        "fillColor": "#0A1628",
        "fillOpacity": 1,
        "strokeColor": "transparent"
      }
    },
    "viz_header": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "# Executive Dashboard\nReal-time business performance metrics",
        "fontColor": "#FFFFFF"
      }
    },
    "viz_bg_kpi_row": {
      "type": "splunk.rectangle",
      "options": {
        "fillColor": "#0D1B2E",
        "fillOpacity": 0.95,
        "strokeColor": "#1A3050",
        "strokeWidth": 1
      }
    },
    "viz_revenue": {
      "type": "splunk.singlevalue",
      "title": "Revenue",
      "dataSources": { "primary": "ds_revenue" },
      "options": {
        "majorFontSize": 42,
        "majorColor": "#FFFFFF",
        "trendDisplay": "sparkline",
        "sparklineDisplay": "below",
        "showSparklineAreaGraph": true,
        "backgroundColor": "transparent",
        "underLabel": "Total Revenue"
      },
      "containerOptions": {
        "title": { "color": "#7B56DB" }
      }
    },
    "viz_users": {
      "type": "splunk.singlevalue",
      "title": "Active Users",
      "dataSources": { "primary": "ds_users" },
      "options": {
        "majorFontSize": 42,
        "majorColor": "#FFFFFF",
        "trendDisplay": "sparkline",
        "sparklineDisplay": "below",
        "showSparklineAreaGraph": true,
        "backgroundColor": "transparent",
        "underLabel": "Unique Users"
      },
      "containerOptions": {
        "title": { "color": "#009CEB" }
      }
    },
    "viz_errors": {
      "type": "splunk.singlevalue",
      "title": "Server Errors",
      "dataSources": { "primary": "ds_errors" },
      "options": {
        "majorFontSize": 42,
        "majorColor": "#DC4E41",
        "trendDisplay": "sparkline",
        "sparklineDisplay": "below",
        "showSparklineAreaGraph": true,
        "backgroundColor": "transparent",
        "underLabel": "5xx Errors"
      },
      "containerOptions": {
        "title": { "color": "#DC4E41" }
      }
    }
  },
  "layout": {
    "globalInputs": ["input_time"],
    "tabs": {
      "items": [{ "layoutId": "layout_1", "label": "KPIs" }]
    },
    "layoutDefinitions": {
      "layout_1": {
        "type": "absolute",
        "options": {
          "display": "auto-scale",
          "width": 1440,
          "height": 900,
          "backgroundColor": "#060B14"
        },
        "structure": [
          { "item": "viz_bg_header", "type": "block", "position": { "x": 0, "y": 0, "w": 1440, "h": 100 } },
          { "item": "viz_header", "type": "block", "position": { "x": 20, "y": 10, "w": 600, "h": 80 } },
          { "item": "viz_bg_kpi_row", "type": "block", "position": { "x": 20, "y": 120, "w": 1400, "h": 250 } },
          { "item": "viz_revenue", "type": "block", "position": { "x": 40, "y": 140, "w": 440, "h": 210 } },
          { "item": "viz_users", "type": "block", "position": { "x": 500, "y": 140, "w": 440, "h": 210 } },
          { "item": "viz_errors", "type": "block", "position": { "x": 960, "y": 140, "w": 440, "h": 210 } }
        ]
      }
    }
  },
  "expressions": {},
  "applicationProperties": {
    "collapseNavigation": true
  }
}
```

---

## Example 3: Interactive Drill-Down with Tokens

Demonstrates: click-to-set-token, conditional panel visibility, default token values, chain search driven by token.

```json
{
  "title": "Network Traffic Analysis",
  "description": "Click a host to see detailed traffic breakdown",
  "inputs": {
    "input_time": {
      "type": "input.timerange",
      "title": "Time Range",
      "options": {
        "token": "global_time",
        "defaultValue": "-4h@h,now"
      }
    }
  },
  "defaults": {
    "dataSources": {
      "ds.search": {
        "options": {
          "queryParameters": {
            "earliest": "$global_time.earliest$",
            "latest": "$global_time.latest$"
          }
        }
      }
    },
    "tokens": {
      "default": {
        "selected_host": { "value": "*" }
      }
    }
  },
  "dataSources": {
    "ds_hosts": {
      "type": "ds.search",
      "options": {
        "query": "index=network | stats sum(bytes) as total_bytes, count as connections by host | sort -total_bytes"
      },
      "name": "Host Summary"
    },
    "ds_host_detail": {
      "type": "ds.search",
      "options": {
        "query": "index=network host=$selected_host|s$ | timechart sum(bytes) as bytes by dest_port"
      },
      "name": "Host Detail"
    },
    "ds_host_table": {
      "type": "ds.search",
      "options": {
        "query": "index=network host=$selected_host|s$ | stats sum(bytes) as bytes, count by dest_ip, dest_port, protocol | sort -bytes"
      },
      "name": "Host Connections"
    }
  },
  "visualizations": {
    "viz_hosts_bar": {
      "type": "splunk.bar",
      "title": "Traffic by Host (click to drill down)",
      "dataSources": { "primary": "ds_hosts" },
      "options": {
        "seriesColors": ["#009CEB"],
        "legendDisplay": "off"
      },
      "eventHandlers": [
        {
          "type": "drilldown.setToken",
          "options": {
            "tokens": [
              { "token": "selected_host", "key": "row.host.value" }
            ]
          }
        }
      ]
    },
    "viz_header_detail": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "## Traffic Detail: $selected_host$",
        "fontColor": "#FFFFFF"
      },
      "containerOptions": {
        "visibility": {
          "showConditions": ["cond_host_selected"]
        }
      }
    },
    "viz_host_timeline": {
      "type": "splunk.area",
      "title": "Bytes Over Time by Port",
      "dataSources": { "primary": "ds_host_detail" },
      "options": {
        "stackMode": "stacked",
        "areaOpacity": 0.6,
        "legendDisplay": "right"
      },
      "containerOptions": {
        "visibility": {
          "showConditions": ["cond_host_selected"]
        }
      }
    },
    "viz_host_connections": {
      "type": "splunk.table",
      "title": "Connection Details",
      "dataSources": { "primary": "ds_host_table" },
      "options": {
        "count": 15,
        "columnFormat": {
          "bytes": {
            "data": "> table | seriesByName(\"bytes\") | formatByType(bytesFormat)"
          }
        }
      },
      "context": {
        "bytesFormat": {
          "number": { "thousandSeparated": true, "precision": 0 }
        }
      },
      "containerOptions": {
        "visibility": {
          "showConditions": ["cond_host_selected"]
        }
      }
    }
  },
  "layout": {
    "globalInputs": ["input_time"],
    "tabs": {
      "items": [{ "layoutId": "layout_1", "label": "Analysis" }]
    },
    "layoutDefinitions": {
      "layout_1": {
        "type": "grid",
        "options": { "width": 1440 },
        "structure": [
          { "item": "viz_hosts_bar", "type": "block", "position": { "x": 0, "y": 0, "w": 1440, "h": 350 } },
          { "item": "viz_header_detail", "type": "block", "position": { "x": 0, "y": 350, "w": 1440, "h": 60 } },
          { "item": "viz_host_timeline", "type": "block", "position": { "x": 0, "y": 410, "w": 1440, "h": 350 } },
          { "item": "viz_host_connections", "type": "block", "position": { "x": 0, "y": 760, "w": 1440, "h": 400 } }
        ]
      }
    }
  },
  "expressions": {
    "conditions": {
      "cond_host_selected": {
        "name": "Host is selected",
        "value": "$selected_host$ != \"*\""
      }
    }
  },
  "applicationProperties": {}
}
```

---

## Example 4: Table with Advanced Column Formatting

Demonstrates: gradient coloring, range-based row colors, number formatting, alternating row backgrounds.

```json
{
  "title": "Service Health Status",
  "description": "Service availability and response metrics with conditional formatting",
  "inputs": {},
  "defaults": {},
  "dataSources": {
    "ds_services": {
      "type": "ds.search",
      "options": {
        "query": "index=monitoring sourcetype=service_health | stats avg(response_time_ms) as avg_response, latest(availability_pct) as availability, latest(status) as status by service_name | eval availability=round(availability,2) | eval avg_response=round(avg_response,0)"
      },
      "name": "Service Health"
    }
  },
  "visualizations": {
    "viz_health_table": {
      "type": "splunk.table",
      "title": "Service Health Matrix",
      "dataSources": { "primary": "ds_services" },
      "options": {
        "count": 25,
        "columnFormat": {
          "status": {
            "rowBackgroundColors": "> table | seriesByName(\"status\") | matchValue(statusBgColors)",
            "rowColors": "> table | seriesByName(\"status\") | matchValue(statusTextColors)"
          },
          "availability": {
            "rowBackgroundColors": "> table | seriesByName(\"availability\") | gradient(availGradient)",
            "data": "> table | seriesByName(\"availability\") | formatByType(pctFormat)"
          },
          "avg_response": {
            "rowBackgroundColors": "> table | seriesByName(\"avg_response\") | rangeValue(responseColors)",
            "data": "> table | seriesByName(\"avg_response\") | formatByType(msFormat)"
          }
        },
        "tableFormat": {
          "rowBackgroundColors": "> table | pick(altRowBg)"
        }
      },
      "context": {
        "statusBgColors": [
          { "match": "healthy", "value": "#1a9035" },
          { "match": "degraded", "value": "#9d6300" },
          { "match": "down", "value": "#b22b2b" }
        ],
        "statusTextColors": [
          { "match": "healthy", "value": "#FFFFFF" },
          { "match": "degraded", "value": "#FFFFFF" },
          { "match": "down", "value": "#FFFFFF" }
        ],
        "availGradient": {
          "stops": [90, 95, 99.9],
          "colors": ["#DC4E41", "#F8BE34", "#53A051"]
        },
        "responseColors": [
          { "to": 200, "value": "#1a3a1a" },
          { "from": 200, "to": 500, "value": "#3a3a1a" },
          { "from": 500, "to": 1000, "value": "#3a2a1a" },
          { "from": 1000, "value": "#3a1a1a" }
        ],
        "pctFormat": {
          "number": { "precision": 2, "unitPosition": "after", "unit": "%" }
        },
        "msFormat": {
          "number": { "precision": 0, "unitPosition": "after", "unit": " ms", "thousandSeparated": true }
        },
        "altRowBg": ["#1A1C20", "#12141A"]
      }
    }
  },
  "layout": {
    "globalInputs": [],
    "tabs": {
      "items": [{ "layoutId": "layout_1", "label": "Health" }]
    },
    "layoutDefinitions": {
      "layout_1": {
        "type": "grid",
        "options": { "width": 1440 },
        "structure": [
          { "item": "viz_health_table", "type": "block", "position": { "x": 0, "y": 0, "w": 1440, "h": 600 } }
        ]
      }
    }
  },
  "expressions": {},
  "applicationProperties": {}
}
```

## Example 5: Application Service Health Monitoring Dashboard

Demonstrates: Proper spacing of visualizations in absolute layout, proper syntax for weekly punchcard visualization

```json
{
  "visualizations": {
    "viz_2dtEyoSf": {
      "type": "splunk.markergauge",
      "options": {
        "orientation": "horizontal",
        "backgroundColor": "#15161A",
        "value": "> primary | seriesByName('performance') | lastPoint()"
      },
      "dataSources": {
        "primary": "ds_lLMVXz2S"
      },
      "title": "",
      "showProgressBar": false,
      "showLastUpdated": false,
      "hideWhenNoData": false
    },
    "viz_3jMwoVYB": {
      "type": "splunk.markergauge",
      "options": {
        "orientation": "horizontal",
        "backgroundColor": "#15161A"
      },
      "dataSources": {
        "primary": "ds_lLMVXz2S"
      },
      "title": "",
      "showProgressBar": false,
      "showLastUpdated": false,
      "hideWhenNoData": false
    },
    "viz_j1y5TVIW": {
      "type": "splunk.markergauge",
      "options": {
        "orientation": "horizontal",
        "backgroundColor": "#15161A"
      },
      "dataSources": {
        "primary": "ds_slxMrH1H_ds_hoDXmuAz_ds_FW49rAx7"
      },
      "title": "",
      "showProgressBar": false,
      "showLastUpdated": false,
      "hideWhenNoData": false
    },
    "viz_fAqdgAnD": {
      "type": "splunk.punchcard",
      "title": "Activity",
      "options": {
        "backgroundColor": "#15161A"
      },
      "dataSources": {
        "primary": "ds_zh1XRYil"
      }
    },
    "viz_uzUManc3": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**Availability**",
        "fontSize": "large"
      }
    },
    "viz_f5Rn9XlO": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**2xx**",
        "fontSize": "extraLarge"
      }
    },
    "viz_nZ1B5gBf": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**Active users**",
        "fontSize": "large"
      }
    },
    "viz_jgkNVV8R": {
      "type": "splunk.column",
      "options": {
        "backgroundColor": "#15161A",
        "xAxisTitleVisibility": "hide",
        "legendDisplay": "bottom"
      },
      "dataSources": {
        "primary": "ds_kBa7cUgt"
      },
      "title": "Memory/CPU During Search Range"
    },
    "viz_Gv4T8Edl": {
      "type": "splunk.pie",
      "options": {
        "backgroundColor": "#15161A"
      },
      "dataSources": {
        "primary": "ds_hoDXmuAz_ds_FW49rAx7"
      },
      "title": "Activity by region"
    },
    "viz_l9d636Mo": {
      "type": "splunk.area",
      "options": {
        "backgroundColor": "#15161A",
        "xAxisTitleVisibility": "hide",
        "y": "> primary | frameBySeriesNames('4xx')",
        "xAxisMaxLabelParts": 2,
        "legendDisplay": "off",
        "yAxisMax": 2500,
        "yAxisMajorTickSize": 3,
        "yAxisMajorTickInterval": 2,
        "yAxisTitleVisibility": "hide"
      },
      "showProgressBar": false,
      "showLastUpdated": false,
      "hideWhenNoData": false,
      "dataSources": {
        "primary": "ds_FW49rAx7"
      },
      "title": "Error rate"
    },
    "viz_OCRGyBxL": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**Performance**",
        "fontSize": "large"
      }
    },
    "viz_PmVeYD7U": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**3xx**",
        "fontSize": "extraLarge"
      }
    },
    "viz_16capbVb": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**4xx**",
        "fontSize": "extraLarge"
      }
    },
    "viz_rnqm1UBP": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**5xx**",
        "fontSize": "extraLarge"
      }
    },
    "viz_SKmPXp6z": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "**xxx**",
        "fontSize": "extraLarge"
      }
    },
    "viz_rYbmxXcF": {
      "type": "splunk.rectangle",
      "options": {
        "strokeColor": "transparent",
        "fillColor": "#7B56DB"
      }
    },
    "viz_5bxGKtNU": {
      "type": "splunk.rectangle",
      "options": {
        "strokeColor": "transparent",
        "fillColor": "#009CEB"
      }
    },
    "viz_Gi7xj4eJ": {
      "type": "splunk.rectangle",
      "options": {
        "strokeColor": "transparent",
        "fillColor": "#00CDAF"
      }
    },
    "viz_oVjFwVZk": {
      "type": "splunk.rectangle",
      "options": {
        "strokeColor": "transparent",
        "fillColor": "#DD9900"
      }
    },
    "viz_1v9R6py1": {
      "type": "splunk.rectangle",
      "options": {
        "strokeColor": "transparent",
        "fillColor": "#FF677B"
      }
    },
    "viz_TU7KaFKb": {
      "type": "splunk.singlevalue",
      "options": {
        "sparklineDisplay": "off",
        "backgroundColor": "transparent"
      },
      "dataSources": {
        "primary": "ds_FW49rAx7"
      }
    },
    "viz_z002TGAG": {
      "type": "splunk.singlevalue",
      "options": {
        "sparklineDisplay": "off",
        "backgroundColor": "transparent",
        "majorValue": "> sparklineValues | lastPoint()",
        "trendValue": "> sparklineValues | delta(-2)",
        "sparklineValues": "> primary | seriesByName('3xx')"
      },
      "dataSources": {
        "primary": "ds_FW49rAx7"
      }
    },
    "viz_hIQnOvtj": {
      "type": "splunk.singlevalue",
      "options": {
        "sparklineDisplay": "off",
        "backgroundColor": "transparent",
        "majorValue": "> sparklineValues | lastPoint()",
        "trendValue": "> sparklineValues | delta(-2)",
        "sparklineValues": "> primary | seriesByName('4xx')"
      },
      "dataSources": {
        "primary": "ds_FW49rAx7"
      }
    },
    "viz_a7Gk4PXz": {
      "type": "splunk.singlevalue",
      "options": {
        "sparklineDisplay": "off",
        "backgroundColor": "transparent",
        "majorValue": "> sparklineValues | lastPoint()",
        "trendValue": "> sparklineValues | delta(-2)",
        "sparklineValues": "> primary | seriesByName('5xx')"
      },
      "dataSources": {
        "primary": "ds_FW49rAx7"
      }
    },
    "viz_hCJj3IQB": {
      "type": "splunk.singlevalue",
      "options": {
        "sparklineDisplay": "off",
        "backgroundColor": "transparent",
        "majorValue": "> sparklineValues | lastPoint()",
        "trendValue": "> sparklineValues | delta(-2)",
        "sparklineValues": "> primary | seriesByName('xxx')"
      },
      "dataSources": {
        "primary": "ds_FW49rAx7"
      }
    },
    "viz_SEcxDErr": {
      "type": "splunk.line",
      "dataSources": {
        "primary": "ds_FW49rAx7"
      },
      "title": "",
      "showProgressBar": false,
      "showLastUpdated": false,
      "hideWhenNoData": false,
      "options": {
        "backgroundColor": "transparent",
        "legendDisplay": "off",
        "xAxisTitleVisibility": "hide"
      }
    },
    "viz_BBVKToiA": {
      "type": "splunk.markdown",
      "options": {
        "markdown": "# **Application Service Health Monitoring**"
      }
    }
  },
  "dataSources": {
    "ds_FW49rAx7": {
      "type": "ds.search",
      "options": {
        "query": "| makeresults count=25 | streamstats count | eval _time=_time-count*3600 | eval 2xx=random()%1000*8.4, 3xx=random()%1000*1.2, 4xx=random()%1000*2.3, 5xx=random()%1000*0.7, xxx=random()%1000*0.2 | fields _time 2xx 3xx 4xx 5xx xxx",
        "queryParameters": {}
      },
      "name": "HTTP status"
    },
    "ds_hoDXmuAz_ds_FW49rAx7": {
      "type": "ds.search",
      "options": {
        "query": "| makeresults count=6 \n| streamstats count\n| eval region=case(count=1, \"North America\", count=2, \"South America\", count=3, \"Europe\", count=4, \"Africa\", count=5, \"Asia\", count=6, \"ANZ\")\n| eval activity=case(count=1,823, count=2,544,count=3, 797, count=4,329, count=5,1016, count=6, 369)\n| fields region activity",
        "queryParameters": {}
      },
      "name": "Activity by region"
    },
    "ds_slxMrH1H_ds_hoDXmuAz_ds_FW49rAx7": {
      "type": "ds.search",
      "options": {
        "query": "| makeresults count=15 \n| streamstats count \n| eval _time=_time-count*3600\n| eval users=random()%100",
        "queryParameters": {}
      },
      "name": "Active users"
    },
    "ds_kBa7cUgt": {
      "type": "ds.search",
      "options": {
        "query": "|makeresults count=100 |streamstats count | eval _time=_time-count*60 | eval memory=random()%100, cpu=random()%100 \n|  fields _time cpu memory",
        "queryParameters": {}
      },
      "name": "Mem and CPU utilization"
    },
    "ds_zh1XRYil": {
      "type": "ds.search",
      "options": {
        "query": "| inputlookup examples.csv | fields punch_hour punch_day punch_count | stats sum(punch_count) by punch_hour punch_day",
        "queryParameters": {}
      },
      "name": "Activity"
    },
    "ds_lLMVXz2S": {
      "type": "ds.search",
      "options": {
        "query": "| makeresults \n| eval performance=91, availability=98",
        "queryParameters": {}
      },
      "name": "Performance and Availability"
    }
  },
  "defaults": {
    "dataSources": {
      "ds.search": {
        "options": {
          "queryParameters": {
            "latest": "$global_time.latest$",
            "earliest": "$global_time.earliest$"
          }
        }
      }
    }
  },
  "inputs": {
    "input_CDJ4CK9c": {
      "options": {
        "defaultValue": "-24h@h,now",
        "token": "global_time"
      },
      "title": "Global Time Range",
      "type": "input.timerange"
    }
  },
  "description": "",
  "title": "Application Service Health Monitoring",
  "layout": {
    "tabs": {
      "items": [
        {
          "layoutId": "layout_1",
          "label": "New tab"
        }
      ]
    },
    "layoutDefinitions": {
      "layout_1": {
        "type": "absolute",
        "options": {
          "width": 1440,
          "height": 960,
          "display": "auto",
          "backgroundImage": {
            "sizeType": "contain",
            "x": 0,
            "y": 0,
            "src": "/static/app/splunk-dashboard-studio/images/examples-hub/application-health-monitoring/monitoring-background.png"
          }
        },
        "structure": [
          {
            "item": "viz_2dtEyoSf",
            "type": "block",
            "position": {
              "x": 980,
              "y": 60,
              "w": 440,
              "h": 160
            }
          },
          {
            "item": "viz_3jMwoVYB",
            "type": "block",
            "position": {
              "x": 980,
              "y": 230,
              "w": 440,
              "h": 160
            }
          },
          {
            "item": "viz_j1y5TVIW",
            "type": "block",
            "position": {
              "x": 980,
              "y": 400,
              "w": 440,
              "h": 160
            }
          },
          {
            "item": "viz_fAqdgAnD",
            "type": "block",
            "position": {
              "x": 740,
              "y": 580,
              "w": 680,
              "h": 360
            }
          },
          {
            "item": "viz_uzUManc3",
            "type": "block",
            "position": {
              "x": 990,
              "y": 240,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_f5Rn9XlO",
            "type": "block",
            "position": {
              "x": 30,
              "y": 70,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_nZ1B5gBf",
            "type": "block",
            "position": {
              "x": 990,
              "y": 410,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_jgkNVV8R",
            "type": "block",
            "position": {
              "x": 20,
              "y": 580,
              "w": 420,
              "h": 360
            }
          },
          {
            "item": "viz_Gv4T8Edl",
            "type": "block",
            "position": {
              "x": 450,
              "y": 580,
              "w": 280,
              "h": 180
            }
          },
          {
            "item": "viz_l9d636Mo",
            "type": "block",
            "position": {
              "x": 450,
              "y": 770,
              "w": 280,
              "h": 170
            }
          },
          {
            "item": "viz_OCRGyBxL",
            "type": "block",
            "position": {
              "x": 990,
              "y": 70,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_PmVeYD7U",
            "type": "block",
            "position": {
              "x": 220,
              "y": 70,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_16capbVb",
            "type": "block",
            "position": {
              "x": 410,
              "y": 70,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_rnqm1UBP",
            "type": "block",
            "position": {
              "x": 600,
              "y": 70,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_SKmPXp6z",
            "type": "block",
            "position": {
              "x": 790,
              "y": 70,
              "w": 140,
              "h": 40
            }
          },
          {
            "item": "viz_rYbmxXcF",
            "type": "block",
            "position": {
              "x": 30,
              "y": 100,
              "w": 150,
              "h": 10
            }
          },
          {
            "item": "viz_5bxGKtNU",
            "type": "block",
            "position": {
              "x": 220,
              "y": 100,
              "w": 150,
              "h": 10
            }
          },
          {
            "item": "viz_Gi7xj4eJ",
            "type": "block",
            "position": {
              "x": 410,
              "y": 100,
              "w": 150,
              "h": 10
            }
          },
          {
            "item": "viz_oVjFwVZk",
            "type": "block",
            "position": {
              "x": 600,
              "y": 100,
              "w": 150,
              "h": 10
            }
          },
          {
            "item": "viz_1v9R6py1",
            "type": "block",
            "position": {
              "x": 790,
              "y": 100,
              "w": 150,
              "h": 10
            }
          },
          {
            "item": "viz_TU7KaFKb",
            "type": "block",
            "position": {
              "x": -40,
              "y": 120,
              "w": 300,
              "h": 50
            }
          },
          {
            "item": "viz_z002TGAG",
            "type": "block",
            "position": {
              "x": 130,
              "y": 120,
              "w": 300,
              "h": 50
            }
          },
          {
            "item": "viz_hIQnOvtj",
            "type": "block",
            "position": {
              "x": 320,
              "y": 120,
              "w": 300,
              "h": 50
            }
          },
          {
            "item": "viz_a7Gk4PXz",
            "type": "block",
            "position": {
              "x": 510,
              "y": 120,
              "w": 300,
              "h": 50
            }
          },
          {
            "item": "viz_hCJj3IQB",
            "type": "block",
            "position": {
              "x": 700,
              "y": 120,
              "w": 300,
              "h": 50
            }
          },
          {
            "item": "viz_SEcxDErr",
            "type": "block",
            "position": {
              "x": 20,
              "y": 170,
              "w": 950,
              "h": 390
            }
          },
          {
            "item": "viz_BBVKToiA",
            "type": "block",
            "position": {
              "x": 20,
              "y": 10,
              "w": 590,
              "h": 40
            }
          }
        ]
      }
    },
    "globalInputs": [
      "input_CDJ4CK9c"
    ],
    "options": {
      "showTitleAndDescription": false
    }
  }
}
```

---

## Common Patterns Quick Reference

### Token-driven search filtering

```json
"query": "index=main host=$host_tok|s$ sourcetype=$st_tok|s$"
```

### Time-range-aware searches via defaults

```json
"defaults": {
  "dataSources": {
    "ds.search": {
      "options": {
        "queryParameters": {
          "earliest": "$global_time.earliest$",
          "latest": "$global_time.latest$"
        }
      }
    }
  }
}
```

### Dynamic dropdown items from search

```json
{
  "type": "input.dropdown",
  "options": {
    "token": "host_tok",
    "defaultValue": "*",
    "items": "> primary | renameSeries(\"label\") | objects()"
  },
  "dataSources": { "primary": "ds_host_list" }
}
```

### Hide panel until user interacts

```json
"containerOptions": {
  "visibility": {
    "showConditions": ["cond_selected"]
  }
}
```

### Conditional severity colors on any chart series

```json
"seriesColorsByField": {
  "critical": "#DC4E41",
  "high": "#F8BE34",
  "medium": "#F1813F",
  "low": "#53A051",
  "info": "#0076D3"
}
```

