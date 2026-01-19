---
description: Scan AWS account for cost optimization
allowed-tools: Read, Task, Write, Bash, Glob, Grep, AskUserQuestion, mcp__awslabs-aws-api__call_aws
---

# AWS Cost Optimization Scan

**Authentication:** AWS commands work with any valid AWS credentials:
- SSO profile: `--profile your-sso-profile`
- Named profile: `--profile your-profile`
- Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`
- IAM role (EC2/Lambda): automatic

## Step 1: Discover Account

```bash
aws sts get-caller-identity --profile {profile}
```

Extract:
- **Account ID** → use in report header
- **Profile name** → use for file naming: `reports/findings_{profile}.json`

## Step 2: Find Active Regions

```bash
# Get all regions
aws ec2 describe-regions --profile {profile} --query 'Regions[].RegionName' --output json

# Check which have EC2 instances (quick check)
aws ec2 describe-instances --profile {profile} --query 'Reservations[].Instances[0].Placement.AvailabilityZone' --output text
```

Only scan regions with resources.

## Step 3: Ask Compliance

Use `AskUserQuestion`:

```json
{
  "questions": [{
    "header": "Compliance",
    "question": "Which compliance requirements apply?",
    "multiSelect": true,
    "options": [
      {"label": "HIPAA", "description": "Healthcare - skip PHI resources"},
      {"label": "SOC2", "description": "Audit - preserve all logs"},
      {"label": "PCI-DSS", "description": "Payments - skip payment infra"},
      {"label": "None", "description": "No compliance requirements"}
    ]
  }]
}
```

## Step 4: Get Actual Monthly Spend

**CRITICAL:** Query AWS Cost Explorer for real billing data.

```bash
aws ce get-cost-and-usage \
  --profile {profile} \
  --time-period Start={LAST_MONTH_START},End={LAST_MONTH_END} \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

Store `actual_monthly_spend` in metadata.

**Note:** If no `--profile` is provided, AWS CLI uses default credentials (env vars or IAM role).

## Step 5: Parallel Domain Scan

Launch 6 `aws-cost-scanner` subagents **in parallel**:

| Agent | Domain | Checks |
|-------|--------|--------|
| 1 | compute | EC2, EBS, AMIs, snapshots, EIPs |
| 2 | storage | S3, EFS, CloudWatch Logs, CloudTrail |
| 3 | database | RDS, DynamoDB, ElastiCache |
| 4 | networking | NAT, ELB, VPC endpoints, data transfer |
| 5 | serverless | Lambda, API Gateway, SQS, Step Functions |
| 6 | reservations | RI coverage, Savings Plans |

Pass to each:
- `region`: Active region(s)
- `compliance`: User's selection
- `profile`: AWS profile name

## Step 6: Merge, Review & Save

Combine all 6 outputs into `reports/findings_{profile}.json`.

**Quick Review (inline - no scripts):**

Apply 2 adjustments only:
1. **Resource Age:** -30% confidence if created < 7 days ago
2. **Environment:** -10% for production, +10% for dev/test (from Name tags)

Mark findings:
- `approved` if confidence ≥ 70%
- `needs_validation` if confidence 50-69%
- `filtered` if confidence < 50%

**Price Validation:** Only flag findings with `monthly_savings > $100` for manual verification. Trust smaller amounts.

## Step 7: Generate Report

Create `reports/cost_report_{profile}.md`:

```markdown
# AWS Cost Optimization Report

**Account:** {account_id}
**Profile:** {profile}
**Date:** {scan_date}
**Compliance:** {compliance}

## Summary

| Metric | Value |
|--------|-------|
| Actual Monthly Spend | $X,XXX |
| Approved Savings | $XXX/mo |
| Needs Validation | $XX/mo |

## Quick Wins (Implement This Week)
...

## Top Savings Opportunities
...

## Needs Validation
...
```

Show user:
1. Total approved savings
2. Top 5 findings
3. Ask which to implement
