import argparse, os, json, hashlib
from diff_utils import get_staged_diff, split_into_hunks
from review import review_hunks
from patcher import apply_unified_patch
from linters import run_ruff, run_bandit, run_mypy
from cost import CostTracker
import yaml
from pathlib import Path

# Rich imports for enhanced CLI experience
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.syntax import Syntax
from rich.tree import Tree
from rich.prompt import Confirm
from rich import box
from rich.text import Text
from rich.columns import Columns

console = Console()

CACHE_DIR = Path(".ai_review_cache")
CACHE_DIR.mkdir(exist_ok=True)

import requests, os

def check_ollama_connection():
    url = os.getenv("OLLAMA_API_URL", "http://localhost:11434/api/generate")
    try:
        resp = requests.post(url, json={"model":"llama3.1:8b","prompt":"ping","stream":False}, timeout=10)
        if resp.status_code == 200:
            console.print(f"[bold green]🔌 Connected to Ollama[/bold green] at [cyan]{url}[/cyan]")
        else:
            console.print(f"[bold yellow]⚠️ Ollama responded with status {resp.status_code}[/bold yellow]")
    except requests.exceptions.Timeout:
        console.print(f"[bold red]❌ Ollama at {url} timed out.[/bold red]")
        raise SystemExit(1)
    except requests.exceptions.RequestException as e:
        console.print(f"[bold red]❌ Could not reach Ollama: {e}[/bold red]")
        raise SystemExit(1)


def cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

def load_yaml(p):
    with open(p) as f:
        return yaml.safe_load(f)

def show_startup_banner(cfg, rules, formats, args=None):
    """Display beautiful startup information"""
    console.print("\n")
    console.print(Panel(
        Text("🤖 RevAI - AI Code Review Assistant", style="bold blue", justify="center"),
        subtitle="[dim]Powered by Ollama LLM • See USER_MANUAL.md for full documentation[/dim]",
        border_style="blue",
        box=box.ROUNDED
    ))
    
    # Determine actual autofix status (CLI args override config)
    autofix_enabled = cfg.get('enable_autofix', False)
    autofix_source = "config"
    
    if args:
        if args.apply_fixes:
            autofix_enabled = True
            autofix_source = "--apply-fixes"
        elif args.no_apply_fixes:
            autofix_enabled = False
            autofix_source = "--no-apply-fixes"
    
    autofix_status = f"[{'green]Enabled' if autofix_enabled else 'red]Disabled'}[/] [dim]({autofix_source})[/dim]"
    
    # Configuration panel
    config_info = [
        f"[bold green]✓[/bold green] Model: [cyan]{cfg.get('model_ollama', 'llama3.1:8b')}[/cyan]",
        f"[bold green]✓[/bold green] Rules: [yellow]{len(rules)}[/yellow] guidelines loaded",
        f"[bold green]✓[/bold green] Formats: [magenta]{', '.join(formats)}[/magenta]",
        f"[bold green]✓[/bold green] Auto-fix: {autofix_status}"
    ]
    
    config_panel = Panel(
        "\n".join(config_info),
        title="[bold]🔧 Configuration[/bold]",
        border_style="green",
        box=box.ROUNDED
    )
    console.print(config_panel)

def show_changes_tree(hunks):
    """Display changed files in a tree structure"""
    if not hunks:
        return
        
    tree = Tree("[bold blue]📁 Changed Files[/bold blue]")
    
    file_groups = {}
    for hunk in hunks:
        path_parts = hunk['file'].split('/')
        if len(path_parts) > 1:
            folder = path_parts[0]
            if folder not in file_groups:
                file_groups[folder] = []
            file_groups[folder].append('/'.join(path_parts[1:]))
        else:
            if 'root' not in file_groups:
                file_groups['root'] = []
            file_groups['root'].append(hunk['file'])
    
    for folder, files in file_groups.items():
        if folder == 'root':
            for file in files:
                tree.add(f"[yellow]📄 {file}[/yellow]")
        else:
            folder_branch = tree.add(f"[blue]📂 {folder}[/blue]")
            for file in files:
                folder_branch.add(f"[yellow]📄 {file}[/yellow]")
    
    console.print(tree)
    console.print("")

def display_review_summary(findings, summary, effort):
    """Display beautiful review summary with rich formatting"""
    # Header panel
    header_text = Text()
    header_text.append("🤖 AI Code Review Complete\n", style="bold blue")
    if summary:
        header_text.append(f"Summary: {summary}\n", style="dim")
    header_text.append(f"Effort Estimate: ", style="dim")
    
    effort_colors = {"XS": "green", "S": "green", "M": "yellow", "L": "red", "XL": "red"}
    header_text.append(f"{effort}", style=f"bold {effort_colors.get(effort, 'blue')}")
    
    header_panel = Panel(
        header_text,
        title="[bold]🎯 Results[/bold]",
        border_style="blue",
        box=box.ROUNDED
    )
    console.print(header_panel)
    
    if not findings:
        console.print(Panel(
            "[bold green]✅ No significant findings detected![/bold green]\n[dim]Your code looks good to go! 🚀[/dim]",
            border_style="green",
            box=box.ROUNDED
        ))
        return
    
    # Findings table
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Severity", style="bold", width=12)
    table.add_column("Rule", style="cyan", width=15)
    table.add_column("Location", style="yellow", width=25)
    table.add_column("Issue", style="white")
    
    severity_icons = {
        "ERROR": "[bold red]🚨 ERROR[/bold red]",
        "WARN": "[bold yellow]⚠️  WARN[/bold yellow]", 
        "INFO": "[bold blue]ℹ️  INFO[/bold blue]"
    }
    
    for f in findings:
        severity = f.get("severity", "").upper()
        table.add_row(
            severity_icons.get(severity, "[dim]❓ UNKNOWN[/dim]"),
            f"[cyan]{f.get('rule', 'GEN')}[/cyan]",
            f"{f.get('file', '?')}:{f.get('line', '?')}",
            f.get('title', 'No description')
        )
    
    console.print(table)
    console.print("")

def display_detailed_findings(findings):
    """Display detailed findings with recommendations"""
    if not findings:
        return
        
    console.print("[bold magenta]📋 Detailed Findings & Recommendations[/bold magenta]\n")
    
    for i, f in enumerate(findings, 1):
        severity = f.get("severity", "").upper()
        severity_colors = {"ERROR": "red", "WARN": "yellow", "INFO": "blue"}
        color = severity_colors.get(severity, "white")
        
        # Finding panel
        finding_text = Text()
        finding_text.append(f"[{severity}] ", style=f"bold {color}")
        finding_text.append(f"{f.get('title', 'No title')}", style="bold")
        finding_text.append(f"\n📍 {f.get('file', '?')}:{f.get('line', '?')}", style="dim")
        
        if f.get('description'):
            finding_text.append(f"\n\n{f.get('description')}", style="")
        
        if f.get('recommendation'):
            finding_text.append(f"\n\n💡 Recommendation: ", style="bold green")
            finding_text.append(f"{f.get('recommendation')}", style="green")
        
        panel = Panel(
            finding_text,
            title=f"[bold]Finding {i}/{len(findings)} - {f.get('rule', 'UNKNOWN')}[/bold]",
            border_style=color,
            box=box.ROUNDED
        )
        console.print(panel)
        console.print("")

def main():
    parser = argparse.ArgumentParser(description="AI Code Review Assistant (Ollama Only)")
    parser.add_argument("--config", default="review_config.yaml", help="Path to config file")
    parser.add_argument("--rules", default="rules.yaml", help="Path to rules file")
    parser.add_argument("--apply-fixes", action="store_true", 
                        help="Enable automatic application of AI suggested fixes (overrides config)")
    parser.add_argument("--no-apply-fixes", action="store_true", 
                        help="Disable automatic fixes (overrides config)")
    parser.add_argument("--format", choices=["md", "json", "sarif"], action="append",
                        help="Output formats")
    parser.add_argument("--display", choices=["compact", "detailed", "summary"], 
                       default="detailed", help="Output display mode")
    args = parser.parse_args()

    cfg = load_yaml(args.config) if os.path.exists(args.config) else {}
    rules = load_yaml(args.rules).get("guidelines", []) if os.path.exists(args.rules) else []
    formats = args.format or cfg.get("formats", ["md"])

    # Backend fixed to Ollama
    backend = "ollama"
    
    # Show beautiful startup banner
    show_startup_banner(cfg, rules, formats, args)

    # Get staged changes with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Analyzing staged changes..."),
        console=console
    ) as progress:
        progress.add_task("Getting diff", total=None)
        diff = get_staged_diff(unified_context=0)
    
    if not diff.strip():
        console.print(Panel(
            "[bold yellow]⚠️  No staged changes found[/bold yellow]\n"
            "[dim]• Use 'git add <files>' to stage files for review[/dim]\n"
            "[dim]• See COMMANDS.md for quick reference[/dim]\n"
            "[dim]• Run 'python cli.py --help' for all options[/dim]",
            border_style="yellow",
            box=box.ROUNDED
        ))
        return 0

    hunks = split_into_hunks(diff)
    tracker = CostTracker()
    
    # Show changed files tree
    show_changes_tree(hunks)

    key = cache_key(diff + backend)
    cache_file = CACHE_DIR / f"{key}.json"
    
    if cache_file.exists():
        console.print("[dim]📋 Using cached analysis...[/dim]")
        report = json.loads(cache_file.read_text())
    else:
        # AI analysis with progress
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold green]🤖 Running AI analysis..."),
            BarColumn(),
            console=console
        ) as progress:
            ai_task = progress.add_task("AI Review", total=100)
            progress.update(ai_task, advance=30)
            
            report = review_hunks(hunks, rules, max_findings=50)
            progress.update(ai_task, advance=100)
            
        cache_file.write_text(json.dumps(report, indent=2))

    # Static analysis with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]🔍 Running static analysis..."),
        console=console
    ) as progress:
        linter_task = progress.add_task("Linters", total=3)
        
        progress.update(linter_task, description="[bold cyan]Running Ruff...[/bold cyan]")
        ruff = run_ruff()
        progress.advance(linter_task)
        
        progress.update(linter_task, description="[bold cyan]Running Bandit...[/bold cyan]")
        bandit = run_bandit()
        progress.advance(linter_task)
        
        progress.update(linter_task, description="[bold cyan]Running MyPy...[/bold cyan]")
        mypy = run_mypy()
        progress.advance(linter_task)

    findings = report.get("findings", [])
    for item in ruff:
        findings.append({
            "file": item["filename"],
            "line": item["location"]["row"],
            "rule": item["code"],
            "severity": "warn",
            "title": item["message"],
            "description": "ruff",
            "recommendation": "Conform to lint rule",
            "auto_fix_patch": ""
        })
    for item in bandit:
        findings.append({
            "file": item.get("filename"),
            "line": item.get("line_number"),
            "rule": f"BANDIT-{item.get('test_id')}",
            "severity": "error" if item.get("issue_severity") == "HIGH" else "warn",
            "title": item.get("issue_text"),
            "description": "bandit",
            "recommendation": "Refactor to mitigate security issue",
            "auto_fix_patch": ""
        })

    out = {
        "summary": report.get("summary", ""),
        "effort": report.get("effort", "S"),
        "findings": findings,
        "mypy": mypy
    }

    # Determine autofix setting (CLI args override config)
    enable_autofix = cfg.get("enable_autofix", False)
    if args.apply_fixes:
        enable_autofix = True
    elif args.no_apply_fixes:
        enable_autofix = False
    
    # Apply auto-fix patches if enabled
    applied = 0
    if enable_autofix:
        fixable_patches = [f for f in findings if f.get("auto_fix_patch")]
        if fixable_patches:
            console.print(f"\n[bold yellow]🛠️  Found {len(fixable_patches)} auto-fixable issues[/bold yellow]")
            console.print("[bold green]🤖 Auto-fix is ENABLED - applying fixes automatically...[/bold green]")
            
            with Progress(
                SpinnerColumn(),
                TextColumn("[bold green]Applying fixes..."),
                BarColumn(),
                console=console
            ) as progress:
                fix_task = progress.add_task("Fixes", total=len(fixable_patches))
                
                for f in fixable_patches:
                    patch = f.get("auto_fix_patch")
                    if patch and apply_unified_patch(patch):
                        applied += 1
                    progress.advance(fix_task)
            
            if applied:
                console.print(f"[bold green]✅ Applied {applied}/{len(fixable_patches)} auto-fix patches and staged them![/bold green]")
            else:
                console.print(f"[bold red]❌ No patches could be applied (may have conflicts)[/bold red]")
    else:
        # Show info about available fixes when autofix is disabled
        fixable_patches = [f for f in findings if f.get("auto_fix_patch")]
        if fixable_patches:
            console.print(f"\n[bold blue]📝 Info: {len(fixable_patches)} auto-fixable issues found[/bold blue]")
            console.print("[dim]Use --apply-fixes to automatically apply suggested fixes[/dim]")

    # --- Output files ---
    console.print("\n[bold blue]📁 Generating Reports[/bold blue]")
    
    if "json" in formats:
        Path("ai_review.json").write_text(json.dumps(out, indent=2))
        console.print("[bold green]💾 Wrote[/bold green] [cyan]ai_review.json[/cyan]")

    if "md" in formats:
        md = ["# AI Review Report\n", f"**Effort**: {out['effort']}\n"]
        if out.get("summary"):
            md.append(f"> {out['summary']}\n")
        if out.get("mypy"):
            md.append("## mypy\n```\n" + out["mypy"] + "\n```\n")
        md.append("## Findings\n")
        for f in findings:
            md.append(f"- **{f['severity'].upper()}** [{f.get('rule','GEN')}] "
                      f"{f['file']}:{f.get('line','?')} — {f['title']}\n"
                      f"  - {f['description']}\n"
                      f"  - **Fix**: {f['recommendation']}\n")
        Path("AI_REVIEW.md").write_text("\n".join(md))
        console.print("[bold green]💾 Wrote[/bold green] [cyan]AI_REVIEW.md[/cyan]")

    # Display results based on chosen mode
    console.print("\n")
    
    if args.display == "summary":
        display_review_summary(findings, out.get("summary"), out.get("effort", "S"))
    elif args.display == "detailed":
        display_review_summary(findings, out.get("summary"), out.get("effort", "S"))
        display_detailed_findings(findings)
    elif args.display == "compact":
        # Compact mode - one line per finding
        if findings:
            console.print("[bold magenta]📋 Quick Summary[/bold magenta]")
            for f in findings:
                severity = f.get("severity", "info").upper()
                icons = {"ERROR": "🚨", "WARN": "⚠️", "INFO": "ℹ️"}
                icon = icons.get(severity, "📌")
                console.print(f"{icon} {f.get('file')}:{f.get('line')} - {f.get('title')}")
        else:
            console.print("[bold green]✅ No issues found![/bold green]")

    if "sarif" in formats:
        sarif = {
            "version": "2.1.0",
            "runs": [{
                "tool": {"driver": {"name": "AIReview", "informationUri": "local"}},
                "results": [{
                    "ruleId": f.get("rule", "AI"),
                    "message": {"text": f.get("title", "Issue")},
                    "level": {"info": "note", "warn": "warning", "error": "error"}[f.get("severity", "info")],
                    "locations": [{
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.get("file", "")},
                            "region": {"startLine": f.get("line", 1)}
                        }
                    }]
                } for f in findings]
            }]
        }
        Path("ai_review.sarif").write_text(json.dumps(sarif, indent=2))
        console.print("[bold green]💾 Wrote[/bold green] [cyan]ai_review.sarif[/cyan]")
    
    # Additional summary from markdown file (legacy compatibility)
    if Path("AI_REVIEW.md").exists() and args.display == "summary":
        console.print("\n[bold blue]📄 Report Summary[/bold blue]")
        lines = Path("AI_REVIEW.md").read_text().splitlines()
        for line in lines:
            if line.strip().startswith("- **"):
                console.print(f"[dim]{line}[/dim]")
        console.print("[dim]Full report saved to AI_REVIEW.md[/dim]\n")

    # Performance summary
    stats = tracker.summary()
    
    perf_panel = Panel(
        f"[bold green]⏱️  Analysis completed in {stats['elapsed_sec']}s[/bold green]\n"
        f"[dim]Characters processed: {stats['chars_in']} in, {stats['chars_out']} out[/dim]",
        title="[bold]📊 Performance[/bold]",
        border_style="green",
        box=box.ROUNDED
    )
    console.print(perf_panel)
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
