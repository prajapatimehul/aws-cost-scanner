"""
AWS Cost Optimizer Output Generators

Markdown-only output for cost optimization analysis results.
"""

from .markdown_report import generate_markdown_report, generate_findings_detail_md

__all__ = [
    'generate_markdown_report',
    'generate_findings_detail_md',
]
