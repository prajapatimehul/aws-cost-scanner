# AWS Cost Optimization Report

**Account:** [REDACTED]
**Region:** eu-central-1
**Date:** 2026-01-28
**Compliance:** HIPAA

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Actual Monthly Spend** | $3,165 |
| **Total Potential Savings** | $1,510/mo |
| **Savings Percentage** | 48% |
| **Findings** | 20 |
| **High Priority** | 5 |

### Spend Breakdown

| Service | Monthly Cost | % of Total |
|---------|-------------|------------|
| RDS | $2,323 | 73% |
| EC2 Compute | $289 | 9% |
| ECS | $185 | 6% |
| VPC | $136 | 4% |
| DMS | $125 | 4% |
| Other | $107 | 3% |

---

## Top Savings Opportunities

### 1. RDS Reserved Instance - $775/mo (HIGH)

| Field | Value |
|-------|-------|
| **Resource** | `app-db` (db.m5.large SQL Server SE) |
| **Current Cost** | $2,323/mo |
| **After RI** | $546/mo (All Upfront 1yr) |
| **Confidence** | 95% |

**Action:** Purchase 1-year All Upfront RDS RI for db.m5.large SQL Server SE.

---

### 2. RDS Downsize Opportunity - $175/mo (MEDIUM)

| Field | Value |
|-------|-------|
| **Resource** | `app-db` (db.m5.large) |
| **CPU Utilization** | 5.27% avg |
| **Connections** | 0.58 avg |
| **Confidence** | 70% |

**Action:** Consider downsizing to db.t3.medium after validating workload requirements.

---

### 3. Compute Savings Plan - $136/mo (HIGH)

| Field | Value |
|-------|-------|
| **Eligible Spend** | $455/mo (EC2 + ECS) |
| **Current Coverage** | 0% |
| **Confidence** | 85% |

**Action:** Purchase $300/mo Compute Savings Plan for 30% savings on EC2 and Fargate.

---

### 4. Idle EC2 Instances - $23/mo (HIGH)

| Instance | Type | CPU Avg | Savings |
|----------|------|---------|---------|
| app-helper-1 | t3.micro | 0.26% | $7.59 |
| app-helper-2 | t3.micro | 0.15% | $7.59 |
| app-bastion | t3.micro | 0.15% | $7.59 |

**Action:** Terminate or schedule stop/start for these idle instances.

---

## Quick Wins (Implement This Week)

| # | Action | Savings | Effort | Risk |
|---|--------|---------|--------|------|
| 1 | Purchase RDS RI | $775/mo | Low | Low |
| 2 | Terminate 3 idle t3.micro instances | $23/mo | Low | Low |
| 3 | Set /ecs/ log retention to 30 days | $9/mo | Low | Low |
| 4 | Create DynamoDB VPC Gateway Endpoint | $3/mo | Low | Low |

**Total Quick Wins: $810/mo**

---

## Summary

| Priority | Action | Monthly Savings |
|----------|--------|-----------------|
| **1** | RDS Reserved Instance | $775 |
| **2** | RDS Downsize (validate first) | $175 |
| **3** | Compute Savings Plan | $136 |
| **4** | EC2 RI | $87 |
| **5** | Terminate idle EC2s | $23 |
| **6** | CloudWatch log retention | $9 |
| **7** | DynamoDB VPC Endpoint | $3 |
| | **TOTAL** | **$1,208/mo** |

**Annualized Savings: $14,496/year**
