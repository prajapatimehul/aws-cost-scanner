# AWS Cost Scanner

A Claude Code plugin with **97 automated cost optimization checks** across 6 AWS domains.

## Prerequisites

Before installing this plugin, you need:

### 1. Install `uv` (Python package manager)

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 2. Configure AWS Credentials

The plugin needs AWS credentials with read access. Choose one method:

**Option A: AWS SSO (Recommended)**
```bash
aws configure sso
aws sso login --profile your-profile
```

**Option B: Access Keys**
```bash
aws configure
# Enter your AWS Access Key ID and Secret Access Key
```

**Option C: Environment Variables**
```bash
export AWS_ACCESS_KEY_ID=your-key
export AWS_SECRET_ACCESS_KEY=your-secret
export AWS_REGION=us-east-1
```

### 3. Required AWS Permissions

Your AWS credentials need read access to:
- EC2 (instances, volumes, snapshots, EIPs)
- RDS (instances, snapshots)
- S3 (buckets, lifecycle)
- Lambda (functions)
- CloudWatch (logs, metrics)
- Cost Explorer (cost and usage data)
- ElastiCache, EFS, DynamoDB

Recommended: Use the `ReadOnlyAccess` managed policy or create a custom policy.

## Installation

### Via Plugin Marketplace

```
/plugin
```
Then search for `prajapatimehul/aws-cost-scanner` and install.

### Via Command Line

```bash
claude mcp add awslabs-aws-api -- uvx awslabs.aws-mcp-server@latest
```

## Quick Start

After installation:

```bash
# Start the scan workflow
/scan

# Or ask directly
Scan my AWS account for cost optimization opportunities
```

## Features

- **Parallel scanning** - 6 domain agents run simultaneously
- **97 checks** across compute, storage, database, networking, serverless, and reservations
- **Confidence scoring** - filters false positives automatically
- **Real pricing** - uses AWS Cost Explorer for accurate spend data
- **Markdown reports** - clean, actionable output

## Domains & Checks

| Domain | Checks | Key Areas |
|--------|--------|-----------|
| **Compute** | 25 | EC2 idle/over-provisioned, EBS unattached, GP2→GP3 |
| **Storage** | 22 | S3 lifecycle, CloudWatch Logs retention, snapshots |
| **Database** | 15 | RDS idle/over-provisioned, RI coverage |
| **Networking** | 15 | Unused EIPs, NAT optimization, VPC endpoints |
| **Serverless** | 10 | Lambda memory, unused functions |
| **Reservations** | 10 | RI/Savings Plans coverage gaps |

## Commands & Skills

| Command | Description |
|---------|-------------|
| `/scan` | Run the full 8-step cost optimization workflow |
| `/reviewing-findings` | Review findings with confidence scoring |
| `/validating-aws-pricing` | Validate pricing against AWS Pricing API |

## Output

Generates:
- `findings.json` - Machine-readable findings
- `reports/cost_report_{profile}.md` - Human-readable report

## Troubleshooting

### "MCP server not found"
Make sure `uv` is installed and in your PATH:
```bash
uv --version
```

### "AWS credentials not configured"
Verify your credentials:
```bash
aws sts get-caller-identity
```

### "Access Denied" errors
Check that your AWS credentials have the required read permissions.

## License

MIT
