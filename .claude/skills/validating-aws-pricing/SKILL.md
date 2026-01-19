---
name: validating-aws-pricing
description: Corrects AWS cost optimization findings with accurate pricing from AWS Pricing API. Updates monthly_savings values in findings.json with real prices for EC2, RDS, EBS, ElastiCache, Lambda, and CloudWatch. Use after generating cost optimization findings to ensure accurate pricing.
allowed-tools:
  - Read
  - Write
  - Bash
  - Grep
  - mcp__awslabs-aws-api__call_aws
---

# Validating AWS Pricing

Validates cost estimates in `findings.json` using **real AWS Pricing API** for big findings (>$100).

## Purpose

This skill validates pricing for significant findings using live AWS Pricing API. Smaller findings use fallback estimates to avoid unnecessary API calls.

## Quick Start

```bash
# Validate with default $100 threshold (queries API only for >$100 findings)
python .claude/skills/validating-aws-pricing/scripts/validate_pricing.py findings.json --profile ctm

# Lower threshold to validate more findings
python .claude/skills/validating-aws-pricing/scripts/validate_pricing.py findings.json --profile ctm --threshold 50

# Works with any AWS auth method (SSO, access keys, IAM role)
python .claude/skills/validating-aws-pricing/scripts/validate_pricing.py findings.json  # uses default credentials
```

## What Gets Updated

For findings **above threshold** (default $100):
1. Queries real AWS Pricing API for EC2, RDS, EBS
2. Updates `monthly_savings` with validated value
3. Marks `api_validated: true` in metadata

For findings **below threshold**:
1. Uses fallback estimates (fast, no API calls)
2. Marks `api_validated: false` in metadata

All findings get `pricing_validated` metadata showing the source.

## Pricing Calculation by Finding Type

### Idle Resources (EC2-001, etc.)
Savings = Full monthly cost of the resource
```python
savings = hourly_rate * 730  # Resource should be terminated
```

### Unattached Storage (EC2-012, EBS-001)
Savings = Storage cost per month
```python
savings = size_gb * price_per_gb  # e.g., 100GB * $0.08 = $8.00
```

### Over-provisioned (RDS-002, LAMBDA-001)
Savings = Difference between current and recommended size
```python
current_cost = current_hourly * 730
recommended_cost = recommended_hourly * 730
savings = current_cost - recommended_cost
```

### No RI Coverage (RDS-005)
Savings = On-Demand cost - Reserved Instance cost
```python
on_demand_monthly = hourly_rate * 730
ri_monthly = ri_upfront / 12 + ri_hourly * 730
savings = on_demand_monthly - ri_monthly  # ~40-60% typically
```

### CloudWatch Logs (SEC-001)
Savings = Storage cost that can be avoided with retention policy
```python
savings = stored_gb * 0.03  # $0.03 per GB-month
```

## AWS Pricing Reference

Current pricing (us-east-1):

| Resource | Price | Unit | Monthly (730 hrs) |
|----------|-------|------|-------------------|
| t2.nano | $0.0058 | /hour | $4.23 |
| t3.nano | $0.0052 | /hour | $3.80 |
| gp3 storage | $0.08 | /GB-month | - |
| db.r5.xlarge | $0.50 | /hour | $365.00 |
| cache.t3.small (Valkey) | $0.0272 | /hour | $19.86 |
| CloudWatch Logs | $0.03 | /GB-month | - |

For complete pricing, see [PRICING_REFERENCE.md](PRICING_REFERENCE.md).

## Output

The script updates `findings.json` in place:

```json
{
  "check_id": "EC2-001",
  "monthly_savings": 4.23,
  "pricing_validated": {
    "source": "AWS Pricing API",
    "validated_at": "2026-01-19T10:00:00Z",
    "hourly_rate": 0.0058,
    "calculation": "0.0058 * 730 hours"
  }
}
```

## Workflow

1. Load `findings.json`
2. For each finding:
   - Identify resource type from `check_id` and `details`
   - Query AWS Pricing API (or use cached known prices)
   - Calculate correct savings based on finding category
   - Update `monthly_savings` field
   - Add `pricing_validated` metadata
3. Recalculate `total_monthly_savings` in metadata
4. Save updated `findings.json`

## Task Checklist

```
- [ ] Load findings.json
- [ ] Query AWS Pricing API for each resource type
- [ ] Calculate correct savings per finding type
- [ ] Update monthly_savings values
- [ ] Recalculate total savings in metadata
- [ ] Save corrected findings.json
- [ ] Regenerate report with accurate prices
```
