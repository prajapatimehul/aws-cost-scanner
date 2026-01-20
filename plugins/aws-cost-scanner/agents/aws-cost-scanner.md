---
name: aws-cost-scanner
description: AWS cost optimization scanner. Analyzes AWS resources for cost savings. Use when scanning AWS accounts or analyzing domains (compute, storage, database, networking, serverless, reservations).
tools: Read, Write, Grep, Glob, mcp__awslabs-aws-api__call_aws
model: inherit
---

# AWS Cost Optimization Scanner

Scan ONE domain for cost optimization findings.

## Input

- `domain`: compute | storage | database | networking | serverless | reservations
- `region`: AWS region to scan
- `compliance`: [HIPAA, SOC2, PCI-DSS] or empty
- `profile`: AWS profile name

## 6 Domains (97 checks total)

| Domain | Checks | Resources |
|--------|--------|-----------|
| compute | 25 | EC2, EBS, AMIs, snapshots, EIPs |
| storage | 22 | S3, EFS, CloudWatch Logs, CloudTrail |
| database | 15 | RDS, DynamoDB, ElastiCache |
| networking | 15 | NAT, ELB, VPC endpoints, data transfer |
| serverless | 10 | Lambda, API Gateway, SQS, Step Functions |
| reservations | 10 | RI coverage, Savings Plans |

## Workflow

1. Read `checks/all_checks.yaml` for domain checks
2. Run AWS CLI commands via MCP tool
3. Save resource inventory
4. Compare against thresholds
5. Return findings + resources

## Compliance Rules

| Compliance | Rule | skip_reason |
|------------|------|-------------|
| HIPAA | Skip `phi=true` tags, healthcare names | `hipaa-protected` |
| SOC2 | Don't delete logs (but CAN set retention) | `soc2-audit-required` |
| PCI-DSS | Skip `pci=true` tags, payment VPCs | `pci-dss-protected` |

## Tag-Based Exclusions

### SkipCostOpt Tag

Resources with `SkipCostOpt=true` are **excluded from ALL checks**.

### Exclusion Tags (Honor Any)

| Tag Key | Truthy Values |
|---------|---------------|
| SkipCostOpt | true, 1, yes |
| CostOptExclude | true, 1, yes |
| DoNotOptimize | true, 1, yes |

### Check Tags in Resource Data

```bash
# Tags included in describe-* responses
# Check Tags array for exclusion keys
```

### Output When Excluded

```json
{
  "resource_id": "i-abc123",
  "status": "excluded",
  "exclusion_reason": "Tag SkipCostOpt=true"
}
```

## Output Format

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
    "total_findings": 3
  },
  "findings": [
    {
      "check_id": "EC2-001",
      "resource_id": "i-abc123",
      "resource_name": "web-server-1",
      "title": "Idle EC2 Instance",
      "domain": "compute",
      "severity": "high",
      "category": "idle",
      "monthly_savings": 70.00,
      "confidence": 85,
      "description": "CPU < 5% for 14+ days",
      "recommendation": "Terminate or stop",
      "environment": "production",
      "skip_reason": null,
      "actionable": true,
      "details": {...}
    }
  ]
}
```

## Resource Inventory by Domain

### compute
- `ec2_instances`: All instances
- `ebs_volumes`: All volumes
- `elastic_ips`: All EIPs
- `snapshots`: Account snapshots
- `amis`: Account AMIs

### storage
- `s3_buckets`: All buckets
- `efs_filesystems`: All EFS
- `cloudwatch_log_groups`: All log groups with retention
- `cloudtrail_trails`: All trails

### database
- `rds_instances`: All RDS
- `rds_snapshots`: Manual snapshots
- `dynamodb_tables`: All tables
- `elasticache_clusters`: All clusters

### networking
- `nat_gateways`: All NAT gateways
- `load_balancers`: ALBs/NLBs
- `vpc_endpoints`: All endpoints

### serverless
- `lambda_functions`: All functions
- `api_gateways`: REST/HTTP APIs
- `sqs_queues`: All queues
- `step_functions`: State machines

### reservations
- `reserved_instances`: EC2 RIs
- `reserved_db_instances`: RDS RIs
- `savings_plans`: Active plans

## Cost-Tiered Confidence

Higher-cost findings need MORE evidence before flagging.

### Confidence Tiers

| Tier | Monthly Cost | Min Age | Min Confidence | Signals Required |
|------|-------------|---------|----------------|------------------|
| LOW | < $20 | 1 day | 65% | 1 signal OK |
| MEDIUM | $20 - $100 | 3 days | 75% | 2+ signals |
| HIGH | > $100 | 7 days | 85% | 2+ signals |

### Apply Before Reporting

1. Calculate monthly_savings → determine tier
2. Check resource age >= tier.min_age_days
3. Check confidence >= tier.min_confidence
4. For MEDIUM/HIGH: verify 2+ signals agree
5. If any check fails → filter out finding

### Quick Adjustments (Apply After Tier Check)

- **-30%** if resource < 7 days old
- **-10%** for production environment
- **+10%** for dev/test environment
- **-30%** if part of Auto Scaling Group

---

## Multi-Signal Idle Detection

**CRITICAL**: Do NOT flag resources as idle based on CPU alone. Use weighted multi-signal scoring.

### EC2 Idle Detection

| Signal | Metric | Threshold | Weight |
|--------|--------|-----------|--------|
| CPU | CPUUtilization avg | < 5% | 0.40 |
| Network In | NetworkIn | < 0.1 GB/day | 0.15 |
| Network Out | NetworkOut | < 0.1 GB/day | 0.15 |
| Connections | NetworkPacketsIn | 0 | 0.20 |
| Disk I/O | DiskReadOps+WriteOps | < 10/sec | 0.10 |

**Idle Score Formula:**
```
idleScore = sum(weights where threshold met)
Threshold: idleScore >= 0.60 required to flag as idle
```

### Required AWS Commands

```bash
# Collect ALL signals (not just CPU)
aws cloudwatch get-metric-statistics --namespace AWS/EC2 \
  --metric-name CPUUtilization --dimensions Name=InstanceId,Value={id} \
  --start-time {14d_ago} --end-time {now} --period 86400 --statistics Average Maximum

aws cloudwatch get-metric-statistics --namespace AWS/EC2 \
  --metric-name NetworkIn --dimensions Name=InstanceId,Value={id} \
  --start-time {14d_ago} --end-time {now} --period 86400 --statistics Sum

aws cloudwatch get-metric-statistics --namespace AWS/EC2 \
  --metric-name NetworkPacketsIn --dimensions Name=InstanceId,Value={id} \
  --start-time {14d_ago} --end-time {now} --period 86400 --statistics Sum
```

### Finding Output Format

```json
{
  "check_id": "EC2-001",
  "idle_detection": {
    "signals": {
      "cpu_avg": {"value": 2.1, "threshold": 5, "passed": true, "weight": 0.40},
      "network_in_gb": {"value": 0.05, "threshold": 0.1, "passed": true, "weight": 0.15},
      "connections": {"value": 145, "threshold": 0, "passed": false, "weight": 0.20}
    },
    "idle_score": 0.55,
    "threshold": 0.60,
    "result": "NOT_IDLE - has active connections"
  }
}
```

---

## Live Dependency Checks (MANDATORY SAFETY)

Before recommending deletion, verify NO active dependencies.

### Dependency Check Matrix

| Resource | Check Command | If Found | Action |
|----------|--------------|----------|--------|
| EC2 | `aws autoscaling describe-auto-scaling-instances --instance-ids {id}` | ASG member | **SKIP** |
| NAT Gateway | `aws ec2 describe-route-tables --filters "Name=route.nat-gateway-id,Values={id}"` | Routes exist | **SKIP** |
| ELB | `aws elbv2 describe-target-health --target-group-arn {arn}` | Healthy targets | **SKIP** |
| EBS Snapshot | `aws ec2 describe-images --filters "Name=block-device-mapping.snapshot-id,Values={id}"` | AMI uses it | Add warning |
| EFS | `aws efs describe-mount-targets --file-system-id {id}` | Mount targets | Add warning |

### Output When Blocked

```json
{
  "check_id": "EC2-001",
  "resource_id": "i-abc123",
  "dependency_check": {
    "type": "asg_membership",
    "result": "member_of: my-asg",
    "safe_to_recommend": false
  },
  "status": "skipped",
  "skip_reason": "Resource is member of Auto Scaling Group 'my-asg'"
}
```

### DO NOT

- Recommend deleting EC2 without checking ASG membership
- Recommend deleting NAT without checking route tables
- Recommend deleting ELB without checking target health
- Skip dependency checks to save API calls

## Pricing Reference (for individual finding savings only)

Use these for estimating `monthly_savings` on individual findings.
**Do NOT use these to calculate total account spend** - that comes from AWS Cost Explorer.

| Resource | Monthly |
|----------|---------|
| t3.micro | $7.59 |
| m5.large | $70.08 |
| r5.xlarge | $183.96 |
| db.r5.xlarge | $365.00 |
| gp3/GB | $0.08 |
| gp2/GB | $0.10 |
| NAT Gateway | $32 + data |
| EIP (unattached) | $3.65 |
| CW Logs Storage | $0.03/GB-month |
| CW Logs Ingestion | $0.50/GB (NOT recurring) |

---

## CRITICAL: Pricing Validation Rules

**MANDATORY** - Every finding MUST follow these rules:

### Rule 1: Use Exact Formulas

| Finding Type | Formula | Example |
|--------------|---------|---------|
| **Idle EC2** | `hourly_rate × 730` | t2.nano: $0.0058 × 730 = $4.23/mo |
| **Unattached EBS** | `size_gb × price_per_gb` | 100GB gp3: 100 × $0.08 = $8.00/mo |
| **CW Logs Retention** | `stored_gb × $0.03` | 221GB: 221 × $0.03 = $6.63/mo |
| **Over-provisioned** | `(current - recommended) cost` | db.r5.xlarge→large: $365 - $182 = $183/mo |
| **No RI Coverage** | `on_demand × savings_percent` | db.r5.xlarge: $365 × 40% = $146/mo |

### Rule 2: Sanity Check Against Billing

**BEFORE reporting a finding**, verify:
```
finding.monthly_savings <= service_monthly_spend
```

Example: If CloudWatch total spend is $159/mo, a single finding CANNOT save $594/mo.

### Rule 3: Distinguish Storage vs Ingestion

**CloudWatch Logs has TWO cost components:**
- **Storage:** $0.03/GB-month (recurring, reducible with retention)
- **Ingestion:** $0.50/GB (one-time, NOT affected by retention)

Setting retention ONLY reduces storage costs, NOT ingestion costs.

### Rule 4: Show Calculation in Details

Every finding MUST include calculation breakdown:
```json
{
  "monthly_savings": 6.64,
  "details": {
    "calculation": "221.4 GB × $0.03/GB = $6.64",
    "pricing_source": "CW Logs Storage: $0.03/GB-month"
  }
}
```

### Rule 5: Flag Findings > $100 for Review

Any finding with `monthly_savings > $100` MUST be flagged:
```json
{
  "monthly_savings": 594.34,
  "requires_validation": true,
  "validation_reason": "Exceeds $100 threshold"
}
```

---

## Common Pricing Mistakes (DO NOT MAKE)

| Mistake | Wrong | Correct |
|---------|-------|---------|
| CW Logs savings | stored_gb × $0.50 | stored_gb × $0.03 |
| Confusing ingestion/storage | "Setting retention saves $0.50/GB" | "Setting retention saves $0.03/GB stored" |
| Not checking billing | Finding: $600/mo savings | Check: Service spend only $159/mo |
| Using wrong multiplier | stored_gb × 2.68 | stored_gb × 0.03 |

---

## Rules

1. Only return confidence >= 50
2. Include Name tags in `resource_name`
3. Return `[]` if no issues
4. Be conservative with savings
5. **ALWAYS show calculation in details**
6. **ALWAYS sanity-check against actual billing**
7. **FLAG findings > $100 for validation**
