# Logging Guide for BV Provisioning Agent

## Overview

Comprehensive logging has been added to track the data flow through the provisioning pipeline. All logs are printed to stdout and visible in the Teams bot logs.

## Log Prefixes

Each tool uses a consistent prefix format:
```
[Tool:tool_name] Log message
```

Examples:
- `[Tool:generate_provisioning_csv]`
- `[Tool:analyze_documents]`
- `[Tool:validate_attributes]`

## What You'll See in the Logs

### 1. `analyze_documents` Tool

**Entry:**
```
[Tool:analyze_documents] Called with directory: /path/to/documents
[Tool:analyze_documents] Found X Excel file(s) in /path/to/spreadsheets
```

**Per File:**
```
[Tool:analyze_documents] Analyzing: filename.xlsx
[Tool:analyze_documents]   Sheet 'Sheet1': 10 rows, 5 columns
[Tool:analyze_documents]     Columns: Name, Email, Extension, Package, Device
[Tool:analyze_documents] ✅ Successfully analyzed filename.xlsx (1 sheets, 10 total rows)
```

**Summary:**
```
[Tool:analyze_documents] ═══════════════════════════════════════
[Tool:analyze_documents] Document Analysis Complete
[Tool:analyze_documents] Total files analyzed: 1
[Tool:analyze_documents] Successful extractions: 1
[Tool:analyze_documents] ═══════════════════════════════════════
```

### 2. `validate_attributes` Tool

**Entry:**
```
[Tool:validate_attributes] Called with 15 extracted attributes
[Tool:validate_attributes] Loaded 80 attribute requirements from template
```

**Summary:**
```
[Tool:validate_attributes] ═══════════════════════════════════════
[Tool:validate_attributes] Validation Complete
[Tool:validate_attributes] ═══════════════════════════════════════
[Tool:validate_attributes] Total attributes: 80
[Tool:validate_attributes] Complete: 15 (18.8%)
[Tool:validate_attributes] Partial: 5
[Tool:validate_attributes] Missing: 60
[Tool:validate_attributes] Conflicts: 0
[Tool:validate_attributes] Critical mandatory missing: 25
[Tool:validate_attributes] ❌ Critical MANDATORY fields missing (first 10):
[Tool:validate_attributes]   - User Details|First Name
[Tool:validate_attributes]   - User Details|Last Name
[Tool:validate_attributes]   ... and 15 more
[Tool:validate_attributes] ═══════════════════════════════════════
```

### 3. `generate_provisioning_csv` Tool

**Entry:**
```
[Tool:generate_provisioning_csv] Called for opportunity: 006Pq00000UKeuTIAT
[Tool:generate_provisioning_csv] Received attributes_data with 15 keys
[Tool:generate_provisioning_csv] Sample attribute keys (first 5):
[Tool:generate_provisioning_csv]   1. User Details|First Name = 'Christi' (status: Complete)
[Tool:generate_provisioning_csv]   2. User Details|Last Name = 'Lewis' (status: Complete)
[Tool:generate_provisioning_csv]   3. User Details|Email = 'clewis@fortispm.com' (status: Complete)
[Tool:generate_provisioning_csv]   4. Location/Address|City = 'Atlanta' (status: Complete)
[Tool:generate_provisioning_csv]   5. Location/Address|State = 'GA' (status: Complete)
```

**OR if empty:**
```
[Tool:generate_provisioning_csv] ⚠️  WARNING: attributes_data is EMPTY - all fields will be 'Missing'
```

**Summary:**
```
[Tool:generate_provisioning_csv] ═══════════════════════════════════════
[Tool:generate_provisioning_csv] CSV Generation Complete
[Tool:generate_provisioning_csv] ═══════════════════════════════════════
[Tool:generate_provisioning_csv] Total attributes: 80
[Tool:generate_provisioning_csv] Populated: 15 (18.8%)
[Tool:generate_provisioning_csv] Missing: 65 (81.2%)
[Tool:generate_provisioning_csv] Inferred: 3
[Tool:generate_provisioning_csv] ═══════════════════════════════════════
[Tool:generate_provisioning_csv] ✅ Populated attributes (first 10):
[Tool:generate_provisioning_csv]   - User Details|First Name
[Tool:generate_provisioning_csv]   - User Details|Last Name
[Tool:generate_provisioning_csv]   - User Details|Email
[Tool:generate_provisioning_csv]   - Location/Address|Street Address
[Tool:generate_provisioning_csv]   - Location/Address|City
[Tool:generate_provisioning_csv]   - Location/Address|State
[Tool:generate_provisioning_csv]   - Location/Address|ZIP Code
[Tool:generate_provisioning_csv]   ... and 3 more
[Tool:generate_provisioning_csv] ❌ Critical MANDATORY attributes still missing (35):
[Tool:generate_provisioning_csv]   - Device Configuration|Device Brand
[Tool:generate_provisioning_csv]   - Device Configuration|Device Model
[Tool:generate_provisioning_csv]   ... and 33 more
[Tool:generate_provisioning_csv] File written to: /path/to/006Pq00000UKeuTIAT_provisioning.csv
[Tool:generate_provisioning_csv] ═══════════════════════════════════════
```

## What to Look For

### Problem: All fields showing "Missing"

**Expected log pattern:**
```
[Tool:generate_provisioning_csv] ⚠️  WARNING: attributes_data is EMPTY - all fields will be 'Missing'
[Tool:generate_provisioning_csv] Populated: 0 (0.0%)
[Tool:generate_provisioning_csv] Missing: 80 (100.0%)
```

**This means:** The agent called `generate_provisioning_csv` without first extracting and building the `attributes_data` dictionary.

### Problem: Some fields extracted but many missing

**Expected log pattern:**
```
[Tool:generate_provisioning_csv] Received attributes_data with 15 keys
[Tool:generate_provisioning_csv] Populated: 15 (18.8%)
[Tool:generate_provisioning_csv] Missing: 65 (81.2%)
```

**This means:** The agent partially extracted data but didn't complete the full 4-pass methodology.

### Success: Most fields populated

**Expected log pattern:**
```
[Tool:generate_provisioning_csv] Received attributes_data with 65 keys
[Tool:generate_provisioning_csv] Populated: 65 (81.2%)
[Tool:generate_provisioning_csv] Missing: 15 (18.8%)
```

**This means:** The agent successfully applied the extraction methodology and populated most attributes.

## Next Steps

1. Run the Teams bot with a test opportunity
2. Share the complete logs (grep for `[Tool:` prefix)
3. We'll analyze:
   - Whether `attributes_data` was populated or empty
   - Which specific attributes were extracted
   - Where the extraction pipeline is failing
