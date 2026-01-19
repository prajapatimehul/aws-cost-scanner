# AWS Cost Scanner

A Claude Code plugin with **97 automated cost optimization checks** across 6 AWS domains.

## Features

- **Parallel scanning** - 6 domain agents run simultaneously
- **97 checks** across compute, storage, database, networking, serverless, and reservations
- **Confidence scoring** - filters false positives automatically
- **Real pricing** - uses AWS Cost Explorer for accurate spend data
- **Markdown reports** - clean, actionable output

## Quick Start

```bash
# Run the scan command
/scan

# Or manually trigger parallel domain scans
claude "Scan my AWS account for cost optimization opportunities"
```

## Domains & Checks

| Domain | Checks | Key Areas |
|--------|--------|-----------|
| **Compute** | 25 | EC2 idle/over-provisioned, EBS unattached, GP2→GP3 |
| **Storage** | 22 | S3 lifecycle, CloudWatch Logs retention, snapshots |
| **Database** | 15 | RDS idle/over-provisioned, RI coverage |
| **Networking** | 15 | Unused EIPs, NAT optimization, VPC endpoints |
| **Serverless** | 10 | Lambda memory, unused functions |
| **Reservations** | 10 | RI/Savings Plans coverage gaps |

## Requirements

- [Claude Code](https://claude.ai/code) CLI
- [AWS MCP Server](https://github.com/awslabs/mcp) configured
- AWS credentials with read access

## Output

Generates:
- `reports/findings_{profile}.json` - Machine-readable findings
- `reports/cost_report_{profile}.md` - Human-readable report

## License

MIT
