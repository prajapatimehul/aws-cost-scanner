# AWS Cost Optimization System

## Overview

97 automated cost optimization checks across 6 domains.
Designed for use with **Claude Code + AWS MCP** for direct account scanning.
Output: **Markdown only** (no Excel/PDF/HTML).

## Quick Start

```bash
# List all checks
python main.py checks

# View specific check
python main.py check EC2-001

# See required AWS CLI commands
python main.py scan-info
```

## How to Scan an AWS Account

Claude Code uses the AWS MCP tool (`mcp__awslabs-aws-api__call_aws`) to scan.

### Step 1: Discover Regions
```
aws ec2 describe-regions --query 'Regions[].RegionName'
```

### Step 2: Get Actual Monthly Spend (CRITICAL)

**Always query AWS Cost Explorer first** to get real billing data:

```bash
aws ce get-cost-and-usage \
  --time-period Start=2025-12-01,End=2026-01-01 \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE
```

This returns actual costs including:
- Data transfer charges
- API request costs
- Marketplace subscriptions
- Taxes and support fees

**Do NOT estimate total spend from resource counts** - it will be wrong.

### Step 3: Run Domain Scans

For each domain, run the AWS CLI commands listed in `checks/all_checks.yaml`.

Example for Compute domain:
```
aws ec2 describe-instances --filters "Name=instance-state-name,Values=running"
aws ec2 describe-volumes --filters "Name=status,Values=available"
aws ec2 describe-addresses
aws ec2 describe-snapshots --owner-ids self
```

### Step 4: Analyze Results

Compare AWS responses against check criteria:
- **EC2-001**: Flag instances with CPU < 5% for 14+ days
- **EC2-012**: Flag unattached EBS volumes
- **NET-001**: Flag unassociated Elastic IPs
- etc.

### Step 5: Generate Report

Save findings to `findings.json`:
```json
{
  "metadata": {
    "account_id": "123456789012",
    "regions": ["us-east-1", "us-west-2"],
    "scan_date": "2024-01-19T10:00:00Z"
  },
  "summary": {
    "actual_monthly_spend": 4111.88,
    "spend_source": "AWS Cost Explorer (December 2025)",
    "total_potential_savings": 656.49
  },
  "findings": [
    {
      "check_id": "EC2-012",
      "resource_id": "vol-abc123",
      "title": "Unattached EBS Volume",
      "domain": "compute",
      "severity": "high",
      "monthly_savings": 50.00,
      "confidence": 95,
      "description": "Volume has been unattached for 30+ days",
      "recommendation": "Snapshot and delete this volume"
    }
  ]
}
```

Then generate markdown:
```bash
python main.py report --findings findings.json
```

## Check Summary (97 Total)

| Domain | Checks | Key Checks |
|--------|--------|------------|
| **Compute** | 25 | EC2 idle, over-provisioned, GP2→GP3, Graviton |
| **Storage** | 22 | S3 lifecycle, EBS unattached, snapshots, CloudWatch Logs, CloudTrail |
| **Database** | 15 | RDS idle, over-provisioned, RI coverage |
| **Networking** | 15 | Unused EIPs, NAT optimization, VPC endpoints |
| **Serverless** | 10 | Lambda memory, unused functions, ARM64 |
| **Reservations** | 10 | RI coverage gaps, Savings Plans |

## Project Structure

```
aws-cost-optimizer/
├── .claude-plugin/
│   └── plugin.json              # Plugin metadata
├── agents/
│   └── aws-cost-scanner.md      # Subagent for parallel domain scanning
├── commands/
│   └── scan.md                  # /scan workflow (7 steps)
├── skills/
│   ├── reviewing-findings/
│   │   ├── reviewing-findings.md    # Skill definition
│   │   ├── REVIEW_CRITERIA.md
│   │   └── scripts/
│   │       └── review_findings.py
│   └── validating-aws-pricing/
│       ├── validating-aws-pricing.md  # Skill definition
│       ├── PRICING_REFERENCE.md
│       └── scripts/
│           └── validate_pricing.py
├── checks/
│   └── all_checks.yaml          # All 97 check definitions with AWS CLI commands
├── src/
│   ├── outputs/
│   │   └── markdown_report.py   # Markdown generator
│   └── parsers/
│       └── cur_parser.py        # CUR file parser (optional)
├── .mcp.json                    # MCP server configuration (AWS API)
├── CLAUDE.md                    # This file
├── README.md                    # Plugin documentation
├── main.py                      # CLI (checks, report)
├── findings.json                # Scan results (generated)
└── resources.json               # Resource inventory (generated)
```

## Custom Subagent: aws-cost-scanner

A specialized subagent for scanning AWS accounts. Located at `agents/aws-cost-scanner.md`.

### Features
- Reads check definitions from `checks/all_checks.yaml`
- Executes AWS CLI commands via MCP tool
- **Saves raw resource inventory** from AWS API responses
- Analyzes results against thresholds
- Outputs both **resources + findings** in JSON format

### Output Format

Each domain scan returns:
```json
{
  "domain": "compute",
  "region": "us-east-1",
  "scanned_at": "2026-01-19T15:00:00Z",
  "resources": {
    "ec2_instances": [...],
    "ebs_volumes": [...]
  },
  "resource_summary": {
    "total_resources": 17,
    "estimated_monthly_cost": 450.00
  },
  "findings": [...]
}
```

This enables:
- "Scanned 45 resources, found 12 issues"
- "Potential savings: $556/mo (22% of total spend)"

### Parallel Domain Scanning

Scan all 6 domains simultaneously for faster analysis:

```
Scan the AWS account in parallel using the aws-cost-scanner agent:
- Launch 6 agents, one for each domain
- Domains: compute, storage, database, networking, serverless, reservations
- Region: us-east-1
```

Claude Code will invoke the Task tool 6 times in parallel:
```python
# Internal invocation (automatic)
Task(
    subagent_type="aws-cost-scanner",
    prompt="Scan the compute domain in us-east-1. Read checks from checks/all_checks.yaml...",
)
# ... repeated for each domain
```

### Single Domain Scan

For focused analysis:
```
Use the aws-cost-scanner agent to scan just the database domain
```

### Manual Invocation

You can also explicitly request parallel scanning:
```
Run 6 aws-cost-scanner agents in parallel:
1. Compute domain
2. Storage domain
3. Database domain
4. Networking domain
5. Serverless domain
6. Reservations domain

Region: us-east-1
After all complete, merge findings into findings.json
```

## AWS MCP Commands Reference

### Compute
```bash
aws ec2 describe-instances
aws ec2 describe-volumes
aws ec2 describe-addresses
aws ec2 describe-snapshots --owner-ids self
aws ec2 describe-images --owners self
aws autoscaling describe-auto-scaling-groups
aws compute-optimizer get-ec2-instance-recommendations
```

### Storage
```bash
aws s3api list-buckets
aws s3api get-bucket-lifecycle-configuration --bucket {name}
aws efs describe-file-systems
aws logs describe-log-groups
aws cloudtrail describe-trails
```

### Database
```bash
aws rds describe-db-instances
aws rds describe-db-snapshots --snapshot-type manual
aws rds describe-reserved-db-instances
aws dynamodb list-tables
aws dynamodb describe-table --table-name {name}
aws elasticache describe-cache-clusters
```

### Networking
```bash
aws ec2 describe-nat-gateways
aws elbv2 describe-load-balancers
aws elbv2 describe-target-groups
aws ec2 describe-vpc-endpoints
aws ec2 describe-vpcs
```

### Serverless
```bash
aws lambda list-functions
aws apigateway get-rest-apis
aws apigatewayv2 get-apis
aws sqs list-queues
aws stepfunctions list-state-machines
```

### Reservations
```bash
aws ce get-reservation-coverage --time-period Start={30d_ago},End={now}
aws ce get-reservation-utilization --time-period Start={30d_ago},End={now}
aws ce get-savings-plans-coverage --time-period Start={30d_ago},End={now}
aws savingsplans describe-savings-plans
aws ec2 describe-reserved-instances
```

### Metrics (CloudWatch)
```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/EC2 \
  --metric-name CPUUtilization \
  --dimensions Name=InstanceId,Value={id} \
  --start-time {14d_ago} \
  --end-time {now} \
  --period 86400 \
  --statistics Average
```

## Finding Format

Each finding should include:
```json
{
  "check_id": "EC2-001",
  "resource_id": "i-abc123",
  "title": "Idle EC2 Instance",
  "domain": "compute",
  "severity": "high",
  "category": "idle",
  "monthly_savings": 150.00,
  "confidence": 90,
  "description": "Instance has <5% CPU utilization for 14+ days",
  "recommendation": "Consider terminating or stopping this instance",
  "details": {
    "instance_type": "m5.large",
    "avg_cpu": 2.3,
    "days_monitored": 21
  }
}
```

## Confidence Scoring

| Score | Meaning | Action |
|-------|---------|--------|
| **≥70%** | Likely correct | Approved |
| **50-69%** | Needs validation | Flag for review |
| **<50%** | Insufficient data | Filter out |

Quick adjustments (2 only):
- **-30%** if resource < 7 days old
- **±10%** based on environment (production = -10%, dev/test = +10%)

## CUR File Support (Optional)

For offline analysis with Cost and Usage Report files:

```python
from src.parsers.cur_parser import CURParser

parser = CURParser()
data = parser.parse('path/to/cur.parquet')
```

Supported formats: Parquet (preferred), CSV

## Severity Levels

| Level | Action | Examples |
|-------|--------|----------|
| **Critical** | Immediate action | Unused resources with high cost |
| **High** | Action within 1 week | Idle instances, unattached volumes |
| **Medium** | Action within 1 month | Over-provisioned, previous gen |
| **Low** | Consider when convenient | Minor optimizations |
| **Info** | Awareness only | Compliance, tagging |

## Scan Workflow (8 Steps)

```
1. Discover account & regions
2. Ask compliance (HIPAA, SOC2, PCI-DSS)
3. Get actual monthly spend from Cost Explorer
4. Parallel domain scan (6 agents)
5. Quick review (2 checks: resource age, environment)
6. MANDATORY: Price validation (sanity check all findings)
7. Generate report
8. Show top findings & ask what to implement
```

### Quick Review (Inline)

Apply 2 adjustments only (no scripts):
- **Resource Age:** -30% confidence if < 7 days old
- **Environment:** -10% for production, +10% for dev/test

Mark findings:
- `approved` if confidence ≥ 70%
- `needs_validation` if confidence 50-69%
- `filtered` if confidence < 50%

### MANDATORY: Price Validation

**CRITICAL** - Run BEFORE generating the report:

1. **Sanity Check:** `finding.monthly_savings <= service.monthly_spend`
   - Example: If CloudWatch costs $159/mo, a finding CANNOT save $594/mo

2. **Verify Formulas:** Each finding type has a specific formula:
   | Finding | Formula |
   |---------|---------|
   | CW Logs Retention | `stored_gb × $0.03` (storage only, NOT $0.50 ingestion) |
   | Unattached EBS | `size_gb × price_per_gb` |
   | Idle EC2 | `hourly_rate × 730` |

3. **For findings > $100:** Query usage-type breakdown:
   ```bash
   aws ce get-cost-and-usage \
     --filter '{"Dimensions": {"Key": "SERVICE", "Values": ["AmazonCloudWatch"]}}' \
     --group-by Type=DIMENSION,Key=USAGE_TYPE
   ```

4. **Correct & Flag:** If a finding fails validation:
   - Recalculate with correct formula
   - Add `pricing_corrected: true` to details
   - Document the correction reason

**Common Mistakes to Avoid:**
- CloudWatch Logs: Using $0.50/GB (ingestion) instead of $0.03/GB (storage)
- Not checking if savings exceed actual service spend
- Missing cost components (EBS has storage + IOPS + throughput)

### Optional: Deep Review

For thorough analysis, run the review script:
```bash
python skills/reviewing-findings/scripts/review_findings.py \
  reports/findings_{profile}.json --profile {profile}
```
