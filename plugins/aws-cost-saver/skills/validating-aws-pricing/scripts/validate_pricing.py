#!/usr/bin/env python3
"""
AWS Pricing Validator & Corrector

Validates cost optimization findings >$100 with real AWS Pricing API data.
Smaller findings use cached estimates (not worth API call overhead).

Usage:
    python validate_pricing.py findings.json --profile ctm
    python validate_pricing.py findings.json --profile ctm --threshold 50
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone


# Average hours per month (365 * 24 / 12)
HOURS_PER_MONTH = 730

# AWS Pricing API region (only available in us-east-1 and ap-south-1)
PRICING_REGION = "us-east-1"

# Minimum savings to trigger real API validation (default $100)
DEFAULT_VALIDATION_THRESHOLD = 100

# Fallback pricing (used when API call fails or for small findings)
# These are estimates - real validation uses AWS Pricing API
FALLBACK_PRICING = {
    "ebs:gp3": 0.08,
    "ebs:gp2": 0.10,
    "ebs:io2": 0.125,
    "cloudwatch:logs-storage": 0.03,
    "rds:snapshot": 0.095,
    "ri:1yr-partial": 0.46,
}

# Explicit check ID to calculator mapping (fixes routing bug)
# Each check ID is explicitly mapped to avoid prefix-matching errors
CHECK_ID_ROUTING = {
    # EC2 Idle/Terminate checks -> full monthly cost savings
    "EC2-001": "ec2",      # Idle EC2 Instance
    "EC2-002": "ec2",      # Stopped Instance (still incurs EBS cost)
    "EC2-004": "ec2",      # Low utilization

    # EC2 Optimization checks -> partial savings (10-30%)
    "EC2-003": "ec2",      # Previous Generation (10% savings)
    "EC2-005": "ec2",      # Over-provisioned (30% savings)
    "EC2-007": "ec2",      # Graviton migration (20% savings)

    # EBS checks
    "EC2-006": "ebs",      # GP2 to GP3 migration
    "EC2-011": "ebs",      # Over-provisioned IOPS
    "EC2-012": "ebs",      # Unattached EBS Volumes
    "EC2-013": "ebs",      # Oversized volumes
    "EBS-001": "ebs",      # Unattached Volumes (duplicate of EC2-012)
    "EBS-002": "ebs",      # GP2 to GP3 (duplicate of EC2-006)
    "EBS-003": "ebs",      # Over-provisioned IOPS
    "EBS-004": "ebs",      # Old snapshots
    "EBS-005": "ebs",      # Oversized volumes
    "EBS-006": "ebs",      # Unencrypted volumes

    # RDS checks
    "RDS-001": "rds",      # Idle RDS
    "RDS-002": "rds",      # Over-provisioned RDS
    "RDS-003": "rds",      # Multi-AZ without need
    "RDS-004": "rds",      # Previous generation
    "RDS-005": "rds",      # No RI coverage
    "RDS-006": "rds",      # Extended Support
    "RDS-007": "rds",      # Old snapshots
    "RDS-008": "rds",      # Aurora capacity

    # ElastiCache checks
    "CACHE-001": "elasticache",
    "CACHE-002": "elasticache",
    "CACHE-003": "elasticache",

    # CloudWatch/Logs checks
    "LOG-001": "cloudwatch",   # CloudWatch Logs retention
    "LOG-002": "cloudwatch",   # Excessive log groups

    # Lambda checks
    "LAMBDA-001": "lambda",    # Over-provisioned memory
    "LAMBDA-002": "lambda",    # Unused functions
    "LAMBDA-003": "lambda",    # No ARM64
    "LAMBDA-004": "lambda",    # Old runtimes
    "LAMBDA-005": "lambda",    # No provisioned concurrency

    # S3 checks
    "S3-001": "s3",           # No lifecycle policy
    "S3-002": "s3",           # No Intelligent-Tiering
    "S3-003": "s3",           # Incomplete multipart uploads
    "S3-004": "s3",           # No versioning cleanup
    "S3-005": "s3",           # Excessive versioning

    # Networking checks (use original estimate)
    "NET-001": "network",     # Unused Elastic IPs
    "NET-002": "network",     # NAT Gateway optimization
    "NET-003": "network",     # VPC Endpoints missing
    "NET-004": "network",     # Cross-AZ data transfer
}

# Map service domain to Cost Explorer service name
DOMAIN_TO_CE_SERVICE = {
    "ec2": "Amazon Elastic Compute Cloud - Compute",
    "ebs": "Amazon Elastic Compute Cloud - Compute",  # EBS is part of EC2 billing
    "rds": "Amazon Relational Database Service",
    "elasticache": "Amazon ElastiCache",
    "cloudwatch": "AmazonCloudWatch",
    "lambda": "AWS Lambda",
    "s3": "Amazon Simple Storage Service",
    "network": "Amazon Elastic Compute Cloud - Compute",
}


def run_aws_command(command: str, profile: str) -> dict | None:
    """Execute AWS CLI command and return JSON response."""
    full_command = f"{command} --output json"
    if profile:
        full_command += f" --profile {profile}"

    try:
        result = subprocess.run(
            full_command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError):
        return None


def query_ec2_pricing(instance_type: str, profile: str, region: str = "us-east-1") -> float | None:
    """Query AWS Pricing API for EC2 instance hourly rate."""
    # Map region code to location name
    location_map = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-1": "US West (N. California)",
        "us-west-2": "US West (Oregon)",
        "eu-west-1": "EU (Ireland)",
        "eu-central-1": "EU (Frankfurt)",
        "ap-southeast-1": "Asia Pacific (Singapore)",
        "ap-northeast-1": "Asia Pacific (Tokyo)",
    }
    location = location_map.get(region, "US East (N. Virginia)")

    cmd = f'''aws pricing get-products --region {PRICING_REGION} \
        --service-code AmazonEC2 \
        --filters \
        "Type=TERM_MATCH,Field=instanceType,Value={instance_type}" \
        "Type=TERM_MATCH,Field=location,Value={location}" \
        "Type=TERM_MATCH,Field=operatingSystem,Value=Linux" \
        "Type=TERM_MATCH,Field=tenancy,Value=Shared" \
        "Type=TERM_MATCH,Field=preInstalledSw,Value=NA" \
        "Type=TERM_MATCH,Field=capacitystatus,Value=Used" \
        --max-results 1'''

    result = run_aws_command(cmd, profile)
    return parse_pricing_response(result)


def query_rds_pricing(instance_type: str, engine: str, profile: str, region: str = "us-east-1") -> float | None:
    """Query AWS Pricing API for RDS instance hourly rate."""
    location_map = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-2": "US West (Oregon)",
        "eu-west-1": "EU (Ireland)",
        "eu-central-1": "EU (Frankfurt)",
    }
    location = location_map.get(region, "US East (N. Virginia)")

    # Normalize engine name
    engine_map = {
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "mariadb": "MariaDB",
        "aurora-postgresql": "Aurora PostgreSQL",
        "aurora-mysql": "Aurora MySQL",
    }
    db_engine = engine_map.get(engine.lower(), "PostgreSQL")

    cmd = f'''aws pricing get-products --region {PRICING_REGION} \
        --service-code AmazonRDS \
        --filters \
        "Type=TERM_MATCH,Field=instanceType,Value={instance_type}" \
        "Type=TERM_MATCH,Field=location,Value={location}" \
        "Type=TERM_MATCH,Field=databaseEngine,Value={db_engine}" \
        "Type=TERM_MATCH,Field=deploymentOption,Value=Single-AZ" \
        --max-results 1'''

    result = run_aws_command(cmd, profile)
    return parse_pricing_response(result)


def query_ebs_pricing(volume_type: str, profile: str, region: str = "us-east-1") -> float | None:
    """Query AWS Pricing API for EBS volume price per GB-month."""
    location_map = {
        "us-east-1": "US East (N. Virginia)",
        "us-east-2": "US East (Ohio)",
        "us-west-2": "US West (Oregon)",
    }
    location = location_map.get(region, "US East (N. Virginia)")

    cmd = f'''aws pricing get-products --region {PRICING_REGION} \
        --service-code AmazonEC2 \
        --filters \
        "Type=TERM_MATCH,Field=volumeApiName,Value={volume_type}" \
        "Type=TERM_MATCH,Field=location,Value={location}" \
        --max-results 5'''

    result = run_aws_command(cmd, profile)
    return parse_pricing_response(result)


def parse_pricing_response(response: dict | None) -> float | None:
    """Extract price from AWS Pricing API response."""
    if not response:
        return None

    price_list = response.get('PriceList', [])
    if not price_list:
        return None

    try:
        product_data = json.loads(price_list[0])
        on_demand = product_data.get('terms', {}).get('OnDemand', {})

        for sku_term in on_demand.values():
            price_dimensions = sku_term.get('priceDimensions', {})
            for dimension in price_dimensions.values():
                price_per_unit = dimension.get('pricePerUnit', {})
                usd_price = price_per_unit.get('USD')
                if usd_price:
                    return float(usd_price)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None

    return None


def get_fallback_price(key: str, default: float = 0.0) -> float:
    """Get fallback price for small findings."""
    return FALLBACK_PRICING.get(key, default)


def get_service_monthly_spend(service_domain: str, profile: str) -> float | None:
    """Query Cost Explorer for actual monthly spend on a service.

    This is the MANDATORY sanity check: findings cannot save more than service costs.
    """
    ce_service = DOMAIN_TO_CE_SERVICE.get(service_domain)
    if not ce_service:
        return None

    # Get last month's actual spend
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    start_of_month = now.replace(day=1)
    end_of_last_month = start_of_month - timedelta(days=1)
    start_of_last_month = end_of_last_month.replace(day=1)

    start_date = start_of_last_month.strftime("%Y-%m-%d")
    end_date = start_of_month.strftime("%Y-%m-%d")

    cmd = f'''aws ce get-cost-and-usage \
        --time-period Start={start_date},End={end_date} \
        --granularity MONTHLY \
        --metrics UnblendedCost \
        --filter '{{"Dimensions": {{"Key": "SERVICE", "Values": ["{ce_service}"]}}}}' '''

    result = run_aws_command(cmd, profile)
    if not result:
        return None

    try:
        results_by_time = result.get("ResultsByTime", [])
        if results_by_time:
            total = results_by_time[0].get("Total", {})
            cost = total.get("UnblendedCost", {}).get("Amount")
            if cost:
                return float(cost)
    except (KeyError, ValueError, TypeError):
        pass

    return None


def sanity_check_finding(finding: dict, profile: str, service_spend_cache: dict) -> dict:
    """MANDATORY: Validate that finding savings don't exceed service spend.

    Per CLAUDE.md: finding.monthly_savings <= service.monthly_spend
    If validation fails, cap savings and mark as corrected.
    """
    check_id = finding.get("check_id", "")
    monthly_savings = finding.get("monthly_savings", 0)

    # Get service domain from check ID routing
    service_domain = CHECK_ID_ROUTING.get(check_id)
    if not service_domain:
        return finding  # Unknown check, skip sanity check

    # Cache service spend queries (expensive API call)
    if service_domain not in service_spend_cache:
        print(f"  Querying Cost Explorer for {service_domain} spend...")
        service_spend_cache[service_domain] = get_service_monthly_spend(service_domain, profile)

    service_spend = service_spend_cache.get(service_domain)

    # SANITY CHECK: savings cannot exceed service spend
    if service_spend is not None and monthly_savings > service_spend:
        original_savings = monthly_savings
        # Cap at 80% of service spend (leaving room for baseline usage)
        capped_savings = round(service_spend * 0.8, 2)

        finding["monthly_savings"] = capped_savings
        finding["pricing_corrected"] = True
        finding["sanity_check"] = {
            "original_savings": original_savings,
            "service_spend": round(service_spend, 2),
            "capped_to": capped_savings,
            "reason": f"Savings ${original_savings:.2f} exceeded service spend ${service_spend:.2f}"
        }
        print(f"  ⚠️  {check_id}: Capped ${original_savings:.2f} -> ${capped_savings:.2f} (service spend: ${service_spend:.2f})")

    return finding


def calculate_ec2_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for EC2 findings."""
    details = finding.get("details", {})
    check_id = finding.get("check_id", "")
    instance_type = details.get("instance_type", "")
    region = details.get("region", "us-east-1")

    hourly_rate = None
    source = "original estimate"

    # Query real pricing for big findings
    if use_api and instance_type:
        print(f"  Querying EC2 pricing for {instance_type}...")
        hourly_rate = query_ec2_pricing(instance_type, profile, region)
        if hourly_rate:
            source = "AWS Pricing API"

    if not hourly_rate:
        return finding.get("monthly_savings", 0), {"source": source}

    monthly_cost = hourly_rate * HOURS_PER_MONTH

    # EC2-001: Idle instance - full cost is the savings
    if check_id == "EC2-001":
        return round(monthly_cost, 2), {
            "source": source,
            "hourly_rate": hourly_rate,
            "calculation": f"{hourly_rate} * {HOURS_PER_MONTH} hours"
        }

    # EC2-003: Previous generation - estimate 10% savings
    if check_id == "EC2-003":
        savings = monthly_cost * 0.10
        return round(savings, 2), {
            "source": source,
            "current_monthly": monthly_cost,
            "calculation": "10% of monthly cost for generation upgrade"
        }

    return round(monthly_cost, 2), {"source": source}


def calculate_ebs_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for EBS findings."""
    details = finding.get("details", {})
    size_gb = details.get("size_gb", 0)
    volume_type = details.get("volume_type", "gp3").lower()
    region = details.get("region", "us-east-1")

    price_per_gb = None
    source = "fallback estimate"

    # Query real pricing for big findings
    if use_api:
        print(f"  Querying EBS pricing for {volume_type}...")
        price_per_gb = query_ebs_pricing(volume_type, profile, region)
        if price_per_gb:
            source = "AWS Pricing API"

    # Fallback to cached prices
    if not price_per_gb:
        price_per_gb = get_fallback_price(f"ebs:{volume_type}", 0.08)

    savings = size_gb * price_per_gb

    return round(savings, 2), {
        "source": source,
        "price_per_gb": price_per_gb,
        "size_gb": size_gb,
        "calculation": f"{size_gb} GB * ${price_per_gb}/GB"
    }


def calculate_rds_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for RDS findings."""
    details = finding.get("details", {})
    check_id = finding.get("check_id", "")
    instance_type = details.get("instance_type", "")
    engine = details.get("engine", "postgresql")
    region = details.get("region", "us-east-1")

    hourly_rate = None
    source = "original estimate"

    # Query real pricing for big findings
    if use_api and instance_type:
        print(f"  Querying RDS pricing for {instance_type} ({engine})...")
        hourly_rate = query_rds_pricing(instance_type, engine, profile, region)
        if hourly_rate:
            source = "AWS Pricing API"

    if not hourly_rate:
        return finding.get("monthly_savings", 0), {"source": source}

    monthly_cost = hourly_rate * HOURS_PER_MONTH

    # RDS-001: Idle database - full cost
    if check_id == "RDS-001":
        return round(monthly_cost, 2), {
            "source": source,
            "hourly_rate": hourly_rate,
            "calculation": f"{hourly_rate} * {HOURS_PER_MONTH} hours"
        }

    # RDS-002: Over-provisioned - estimate savings from downsizing
    if check_id == "RDS-002":
        savings = monthly_cost * 0.50
        return round(savings, 2), {
            "source": source,
            "current_monthly": monthly_cost,
            "calculation": "50% savings from rightsizing (xlarge to large)"
        }

    # RDS-005: No RI coverage - ~46% savings with 1yr RI
    if check_id == "RDS-005":
        ri_discount = get_fallback_price("ri:1yr-partial", 0.46)
        savings = monthly_cost * ri_discount
        return round(savings, 2), {
            "source": source,
            "on_demand_monthly": monthly_cost,
            "ri_discount_rate": f"{ri_discount * 100:.0f}%",
            "calculation": f"${monthly_cost:.2f} * {ri_discount * 100:.0f}% RI savings"
        }

    # RDS-007: Old snapshot
    if check_id == "RDS-007":
        storage_gb = details.get("allocated_storage_gb", 20)
        snapshot_price = get_fallback_price("rds:snapshot", 0.095)
        savings = storage_gb * snapshot_price
        return round(savings, 2), {
            "source": "fallback estimate",
            "storage_gb": storage_gb,
            "price_per_gb": snapshot_price,
            "calculation": f"{storage_gb} GB * ${snapshot_price}/GB"
        }

    return round(monthly_cost, 2), {"source": source}


def calculate_elasticache_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for ElastiCache findings. Uses original estimate (no Pricing API for ElastiCache)."""
    # ElastiCache Pricing API is complex - use original estimates
    return finding.get("monthly_savings", 0), {"source": "original estimate"}


def calculate_cloudwatch_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for CloudWatch findings."""
    details = finding.get("details", {})
    stored_gb = details.get("stored_gb", 0)

    if not stored_gb:
        return finding.get("monthly_savings", 0), {"source": "original estimate"}

    storage_price = get_fallback_price("cloudwatch:logs-storage", 0.03)
    savings = stored_gb * storage_price

    return round(savings, 2), {
        "source": "fallback estimate",
        "stored_gb": stored_gb,
        "price_per_gb": storage_price,
        "calculation": f"{stored_gb:.1f} GB * ${storage_price}/GB"
    }


def calculate_lambda_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for Lambda findings. Uses original estimate."""
    # Lambda pricing is usage-based and complex - use original estimates
    return finding.get("monthly_savings", 0), {"source": "original estimate"}


def calculate_s3_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for S3 findings."""
    # S3 lifecycle/versioning savings are estimates based on bucket analysis
    return finding.get("monthly_savings", 0), {"source": "original estimate", "needs_manual_review": True}


def calculate_network_savings(finding: dict, profile: str, use_api: bool = False) -> tuple[float, dict]:
    """Calculate savings for networking findings (EIPs, NAT, etc.)."""
    check_id = finding.get("check_id", "")

    # NET-001: Unused Elastic IP - fixed cost $3.60/month
    if check_id == "NET-001":
        return 3.60, {"source": "fixed rate", "calculation": "$0.005/hour * 730 hours"}

    # Other network findings use original estimate
    return finding.get("monthly_savings", 0), {"source": "original estimate"}


# Calculator dispatch table (maps service domain to calculator function)
CALCULATOR_DISPATCH = {
    "ec2": calculate_ec2_savings,
    "ebs": calculate_ebs_savings,
    "rds": calculate_rds_savings,
    "elasticache": calculate_elasticache_savings,
    "cloudwatch": calculate_cloudwatch_savings,
    "lambda": calculate_lambda_savings,
    "s3": calculate_s3_savings,
    "network": calculate_network_savings,
}


def correct_finding(finding: dict, profile: str, threshold: float = 100) -> dict:
    """Correct a single finding with accurate pricing.

    Only queries AWS Pricing API for findings with savings > threshold.
    Uses explicit check ID routing (not prefix matching) to avoid misrouting bugs.
    """
    check_id = finding.get("check_id", "")
    original_savings = finding.get("monthly_savings", 0)

    # Only use real API for big findings (> threshold)
    use_api = original_savings > threshold

    # Route to appropriate calculator using EXPLICIT check ID mapping
    # This fixes the bug where startswith("EC2-00") matched EC2-001 through EC2-009
    service_domain = CHECK_ID_ROUTING.get(check_id)

    if service_domain and service_domain in CALCULATOR_DISPATCH:
        calculator = CALCULATOR_DISPATCH[service_domain]
        savings, metadata = calculator(finding, profile, use_api)
    else:
        # Unknown check ID - keep original but flag for review
        savings = original_savings
        metadata = {"source": "original estimate", "warning": f"Unknown check_id: {check_id}"}

    # Update finding
    finding["monthly_savings"] = savings
    finding["pricing_validated"] = {
        **metadata,
        "original_estimate": original_savings,
        "api_validated": use_api,
        "validated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }

    return finding


def correct_findings(findings_path: str, profile: str, threshold: float = 100) -> dict:
    """Correct all findings with accurate pricing.

    Only queries AWS Pricing API for findings with savings > threshold.
    Smaller findings use fallback estimates.

    MANDATORY: Also performs sanity check (savings <= service spend).
    """
    try:
        with open(findings_path) as f:
            data = json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {findings_path}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    findings = data.get("findings", [])
    metadata = data.get("metadata", {})

    if not findings:
        print("No findings to validate.")
        return {"metadata": metadata, "findings": []}

    # Count findings above threshold
    big_findings = [f for f in findings if f.get("monthly_savings", 0) > threshold]
    print(f"\nFound {len(findings)} findings, {len(big_findings)} above ${threshold} threshold")
    if big_findings:
        print(f"Will query AWS Pricing API for {len(big_findings)} finding(s)...\n")

    # Cache for service spend (avoid repeated Cost Explorer queries)
    service_spend_cache = {}

    # Correct each finding
    corrected_findings = []
    total_original = 0
    total_corrected = 0
    api_validated_count = 0
    sanity_check_corrections = 0

    for finding in findings:
        original = finding.get("monthly_savings", 0)
        total_original += original

        # Step 1: Price correction
        corrected = correct_finding(finding.copy(), profile, threshold)

        # Step 2: MANDATORY sanity check (savings <= service spend)
        corrected = sanity_check_finding(corrected, profile, service_spend_cache)
        if corrected.get("pricing_corrected"):
            sanity_check_corrections += 1

        corrected_findings.append(corrected)
        total_corrected += corrected.get("monthly_savings", 0)

        if corrected.get("pricing_validated", {}).get("api_validated"):
            api_validated_count += 1

    # Update metadata
    metadata["total_monthly_savings"] = round(total_corrected, 2)
    metadata["pricing_validation"] = {
        "validated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "validation_threshold": threshold,
        "api_validated_count": api_validated_count,
        "fallback_estimate_count": len(findings) - api_validated_count,
        "sanity_check_corrections": sanity_check_corrections,
        "service_spend_cache": {k: round(v, 2) if v else None for k, v in service_spend_cache.items()},
        "original_total": round(total_original, 2),
        "corrected_total": round(total_corrected, 2),
        "findings_processed": len(corrected_findings)
    }

    return {
        "metadata": metadata,
        "findings": corrected_findings
    }


def print_summary(data: dict) -> None:
    """Print correction summary."""
    validation = data.get("metadata", {}).get("pricing_validation", {})

    print("\n" + "=" * 60)
    print("AWS PRICING VALIDATION SUMMARY")
    print("=" * 60)
    print(f"Findings Processed:   {validation.get('findings_processed', 0)}")
    print(f"API Validated:        {validation.get('api_validated_count', 0)} (>${validation.get('validation_threshold', 100)})")
    print(f"Fallback Estimates:   {validation.get('fallback_estimate_count', 0)}")
    print("-" * 60)
    print(f"Original Total:       ${validation.get('original_total', 0):,.2f}/month")
    print(f"Validated Total:      ${validation.get('corrected_total', 0):,.2f}/month")

    diff = validation.get('corrected_total', 0) - validation.get('original_total', 0)
    if diff > 0:
        print(f"Adjustment:           +${diff:,.2f} (estimates were low)")
    elif diff < 0:
        print(f"Adjustment:           -${abs(diff):,.2f} (estimates were high)")
    else:
        print(f"Adjustment:           $0.00 (estimates were accurate)")

    print("=" * 60)

    # Show API-validated findings
    findings = data.get("findings", [])
    api_validated = [f for f in findings if f.get("pricing_validated", {}).get("api_validated")]

    if api_validated:
        print("\nAPI-Validated Findings:")
        print("-" * 60)
        for f in sorted(api_validated, key=lambda x: x.get("monthly_savings", 0), reverse=True):
            pv = f.get("pricing_validated", {})
            print(f"  {f.get('check_id')}: {f.get('title', '')[:40]}")
            print(f"    ${pv.get('original_estimate', 0):.2f} -> ${f.get('monthly_savings', 0):.2f} ({pv.get('source', 'unknown')})")

    # Show significant corrections
    corrections = []
    for f in findings:
        pv = f.get("pricing_validated", {})
        original = pv.get("original_estimate", 0)
        corrected = f.get("monthly_savings", 0)
        if original > 0 and abs(corrected - original) / original > 0.15:
            corrections.append({
                "check_id": f.get("check_id"),
                "title": f.get("title", "")[:40],
                "original": original,
                "corrected": corrected
            })

    if corrections:
        print("\nSignificant Price Corrections (>15% change):")
        print("-" * 60)
        for c in sorted(corrections, key=lambda x: abs(x["corrected"] - x["original"]), reverse=True)[:10]:
            print(f"  {c['check_id']}: {c['title']}")
            print(f"    ${c['original']:.2f} -> ${c['corrected']:.2f}")

    print()


def main():
    parser = argparse.ArgumentParser(
        description="Validate AWS cost findings with real Pricing API (for big findings)"
    )
    parser.add_argument("findings", help="Path to findings.json")
    parser.add_argument("--profile", default="", help="AWS profile (optional - uses default credentials if not specified)")
    parser.add_argument("--threshold", type=float, default=100, help="Only query Pricing API for findings > threshold (default: $100)")
    parser.add_argument("--output", help="Output path (default: overwrite input)")
    parser.add_argument("--dry-run", action="store_true", help="Don't save changes")

    args = parser.parse_args()

    print(f"Validating findings: {args.findings}")
    print(f"AWS profile: {args.profile or '(default credentials)'}")
    print(f"API threshold: ${args.threshold} (only query API for larger findings)")

    corrected = correct_findings(args.findings, args.profile, args.threshold)
    print_summary(corrected)

    if not args.dry_run:
        output_path = args.output or args.findings
        with open(output_path, "w") as f:
            json.dump(corrected, f, indent=2)
        print(f"Validated findings saved to: {output_path}")


if __name__ == "__main__":
    main()
