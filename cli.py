import argparse, os, json, hashlib
from diff_utils import get_staged_diff, split_into_hunks
from review import review_hunks
from patcher import apply_unified_patch
from linters import run_ruff, run_bandit, run_mypy
from cost import CostTracker
from feedback_tracker import FeedbackTracker, FeedbackStatus
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
    
    # Findings table with feedback status
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("Severity", style="bold", width=12)
    table.add_column("Rule", style="cyan", width=12)
    table.add_column("Location", style="yellow", width=20)
    table.add_column("Feedback", style="bold", width=12)
    table.add_column("Issue", style="white")
    
    severity_icons = {
        "ERROR": "[bold red]🚨 ERROR[/bold red]",
        "WARN": "[bold yellow]⚠️  WARN[/bold yellow]", 
        "INFO": "[bold blue]ℹ️  INFO[/bold blue]"
    }
    
    feedback_icons = {
        "open": "[bold blue]🔓 Open[/bold blue]",
        "resolved": "[bold green]✅ Done[/bold green]", 
        "false_positive": "[bold orange1]🚫 FP[/bold orange1]",
        "will_fix_later": "[bold yellow]⏳ Later[/bold yellow]",
        "acknowledged": "[bold cyan]👁️  Seen[/bold cyan]",
        "in_progress": "[bold magenta]🔧 WIP[/bold magenta]"
    }
    
    for f in findings:
        severity = f.get("severity", "").upper()
        feedback_status = f.get("feedback_status", "open")
        
        table.add_row(
            severity_icons.get(severity, "[dim]❓ UNKNOWN[/dim]"),
            f"[cyan]{f.get('rule', 'GEN')}[/cyan]",
            f"{f.get('file', '?')}:{f.get('line', '?')}",
            feedback_icons.get(feedback_status, f"[dim]{feedback_status}[/dim]"),
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
        
        # Finding panel with feedback info
        finding_text = Text()
        finding_text.append(f"[{severity}] ", style=f"bold {color}")
        finding_text.append(f"{f.get('title', 'No title')}", style="bold")
        finding_text.append(f"\n📍 {f.get('file', '?')}:{f.get('line', '?')}", style="dim")
        
        # Add feedback status and ID
        feedback_status = f.get("feedback_status", "open")
        feedback_colors = {"resolved": "green", "false_positive": "orange1", "will_fix_later": "yellow", "open": "blue"}
        feedback_color = feedback_colors.get(feedback_status, "white")
        
        finding_text.append(f"\n🏷️  Status: ", style="dim")
        finding_text.append(f"{feedback_status.replace('_', ' ').title()}", style=f"bold {feedback_color}")
        
        if f.get('finding_id'):
            finding_text.append(f"\n🆔 ID: ", style="dim")
            finding_text.append(f"{f.get('finding_id')}", style="cyan")
        
        if f.get('feedback_count', 0) > 0:
            finding_text.append(f"\n💬 Comments: ", style="dim")
            finding_text.append(f"{f.get('feedback_count')}", style="yellow")
        
        if f.get('description'):
            finding_text.append(f"\n\n{f.get('description')}", style="")
        
        if f.get('recommendation'):
            finding_text.append(f"\n\n💡 Recommendation: ", style="bold green")
            finding_text.append(f"{f.get('recommendation')}", style="green")
        
        # Add feedback management hint
        if f.get('finding_id'):
            finding_text.append(f"\n\n[dim]💡 Use: python cli.py --feedback comment --finding-id {f.get('finding_id')} --message \"your comment\"[/dim]", style="")
        
        panel = Panel(
            finding_text,
            title=f"[bold]Finding {i}/{len(findings)} - {f.get('rule', 'UNKNOWN')}[/bold]",
            border_style=color,
            box=box.ROUNDED
        )
        console.print(panel)
        console.print("")

def handle_feedback_operations(args) -> int:
    """Handle all feedback-related operations"""
    feedback_tracker = FeedbackTracker()
    
    if args.feedback == "list":
        return handle_feedback_list(feedback_tracker, args)
    elif args.feedback == "show":
        return handle_feedback_show(feedback_tracker, args)
    elif args.feedback == "comment":
        return handle_feedback_comment(feedback_tracker, args)
    elif args.feedback == "resolve":
        return handle_feedback_resolve(feedback_tracker, args)
    elif args.feedback == "false-positive":
        return handle_feedback_false_positive(feedback_tracker, args)
    elif args.feedback == "will-fix-later":
        return handle_feedback_will_fix_later(feedback_tracker, args)
    elif args.feedback == "stats":
        return handle_feedback_stats(feedback_tracker, args)
    elif args.feedback == "search":
        return handle_feedback_search(feedback_tracker, args)
    else:
        console.print("[bold red]❌ Unknown feedback operation[/bold red]")
        return 1

def handle_feedback_list(feedback_tracker: FeedbackTracker, args) -> int:
    """List all findings with feedback"""
    findings = feedback_tracker.list_findings(status=args.status, author=args.author)
    
    if not findings:
        console.print("[bold yellow]📋 No findings match the criteria[/bold yellow]")
        return 0
    
    # Create findings table
    table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
    table.add_column("ID", style="cyan", width=12)
    table.add_column("Status", style="bold", width=15)
    table.add_column("File:Line", style="yellow", width=25)
    table.add_column("Rule", style="green", width=12)
    table.add_column("Title", style="white")
    table.add_column("Comments", style="blue", width=8)
    
    status_colors = {
        "open": "[bold blue]🔓 Open[/bold blue]",
        "resolve": "[bold green]✅ Resolved[/bold green]", 
        "false_positive": "[bold orange1]🚫 False Positive[/bold orange1]",
        "will_fix_later": "[bold yellow]⏳ Will Fix Later[/bold yellow]"
    }
    
    for finding_id, finding_data in findings.items():
        table.add_row(
            finding_id,
            status_colors.get(finding_data["status"], finding_data["status"]),
            f"{finding_data['file']}:{finding_data['line']}",
            finding_data["rule"],
            finding_data["title"][:50] + ("..." if len(finding_data["title"]) > 50 else ""),
            str(len(finding_data["discussion"]))
        )
    
    console.print(f"\n[bold blue]📋 Found {len(findings)} findings[/bold blue]")
    console.print(table)
    return 0

def handle_feedback_show(feedback_tracker: FeedbackTracker, args) -> int:
    """Show detailed feedback for a specific finding"""
    if not args.finding_id:
        console.print("[bold red]❌ --finding-id required for show operation[/bold red]")
        return 1
    
    finding_data = feedback_tracker.get_finding_feedback(args.finding_id)
    if not finding_data:
        console.print(f"[bold red]❌ Finding {args.finding_id} not found[/bold red]")
        return 1
    
    # Display finding details
    status_colors = {
        "open": "blue", "resolved": "green", 
        "false_positive": "orange1", "will_fix_later": "yellow"
    }
    color = status_colors.get(finding_data.status, "white")
    
    finding_panel = Panel(
        f"[bold]File:[/bold] {finding_data.file}:{finding_data.line}\n"
        f"[bold]Rule:[/bold] {finding_data.rule}\n"
        f"[bold]Title:[/bold] {finding_data.title or 'No title'}\n"
        f"[bold]Status:[/bold] [{color}]{finding_data.status.replace('_', ' ').title()}[/{color}]\n"
        f"[bold]Created:[/bold] {finding_data.created_at[:19]}",
        title=f"[bold]Finding {args.finding_id}[/bold]",
        border_style=color,
        box=box.ROUNDED
    )
    console.print(finding_panel)
    
    # Display discussion
    if finding_data.entries:
        console.print(f"\n[bold magenta]💬 Discussion ({len(finding_data.entries)} messages)[/bold magenta]")
        
        for i, entry in enumerate(finding_data.entries, 1):
            timestamp = entry.timestamp[:19].replace("T", " ")
            action_icons = {
                "comment": "💬", "reply": "↳", "resolve": "✅", "status_change": "🔄",
                "false_positive": "🚫", "will_fix_later": "⏳", "created": "📝"
            }
            icon = action_icons.get(entry.action, "📝")
            
            message_panel = Panel(
                f"[dim]{timestamp}[/dim]\n{entry.message}",
                title=f"{icon} {entry.author} - {entry.action}",
                border_style="dim",
                box=box.ROUNDED
            )
            console.print(message_panel)
    else:
        console.print("\n[dim]No discussion yet[/dim]")
    
    return 0

def handle_feedback_comment(feedback_tracker: FeedbackTracker, args) -> int:
    """Add comment to a finding"""
    if not args.finding_id:
        console.print("[bold red]❌ --finding-id required for comment operation[/bold red]")
        return 1
    
    if not args.message:
        console.print("[bold red]❌ --message required for comment operation[/bold red]")
        return 1
    
    success = feedback_tracker.add_comment(args.finding_id, args.message, args.author)
    if success:
        console.print(f"[bold green]✅ Comment added to finding {args.finding_id}[/bold green]")
        return 0
    else:
        console.print(f"[bold red]❌ Failed to add comment to finding {args.finding_id}[/bold red]")
        return 1

def handle_feedback_resolve(feedback_tracker: FeedbackTracker, args) -> int:
    """Mark finding as resolved"""
    if not args.finding_id:
        console.print("[bold red]❌ --finding-id required for resolve operation[/bold red]")
        return 1
    
    message = args.message or "Marked as resolved"
    success = feedback_tracker.mark_resolved(args.finding_id, message, args.author)
    if success:
        console.print(f"[bold green]✅ Finding {args.finding_id} marked as resolved[/bold green]")
        return 0
    else:
        console.print(f"[bold red]❌ Failed to resolve finding {args.finding_id}[/bold red]")
        return 1

def handle_feedback_false_positive(feedback_tracker: FeedbackTracker, args) -> int:
    """Mark finding as false positive"""
    if not args.finding_id:
        console.print("[bold red]❌ --finding-id required for false-positive operation[/bold red]")
        return 1
    
    message = args.message or "Marked as false positive"
    success = feedback_tracker.mark_false_positive(args.finding_id, message, args.author)
    if success:
        console.print(f"[bold orange1]🚫 Finding {args.finding_id} marked as false positive[/bold orange1]")
        return 0
    else:
        console.print(f"[bold red]❌ Failed to mark finding {args.finding_id} as false positive[/bold red]")
        return 1

def handle_feedback_will_fix_later(feedback_tracker: FeedbackTracker, args) -> int:
    """Mark finding as will fix later"""
    if not args.finding_id:
        console.print("[bold red]❌ --finding-id required for will-fix-later operation[/bold red]")
        return 1
    
    message = args.message or "Will fix in future iteration"
    success = feedback_tracker.mark_will_fix_later(args.finding_id, message, args.author)
    if success:
        console.print(f"[bold yellow]⏳ Finding {args.finding_id} marked as will fix later[/bold yellow]")
        return 0
    else:
        console.print(f"[bold red]❌ Failed to mark finding {args.finding_id} as will fix later[/bold red]")
        return 1

def handle_feedback_stats(feedback_tracker: FeedbackTracker, args) -> int:
    """Show feedback statistics"""
    stats = feedback_tracker.get_finding_stats()
    
    # Overview panel
    overview_panel = Panel(
        f"[bold]Total Findings:[/bold] {stats['total_findings']}\n"
        f"[bold]Total Comments:[/bold] {stats['total_comments']}\n"
        f"[bold]Resolution Rate:[/bold] {stats['resolution_rate']}%",
        title="[bold blue]📊 Feedback Overview[/bold blue]",
        border_style="blue",
        box=box.ROUNDED
    )
    console.print(overview_panel)
    
    # Status breakdown
    if stats['by_status']:
        status_table = Table(show_header=True, header_style="bold magenta", box=box.ROUNDED)
        status_table.add_column("Status", style="bold")
        status_table.add_column("Count", style="cyan", justify="right")
        
        status_names = {
            "open": "🔓 Open",
            "resolve": "✅ Resolved", 
            "false_positive": "🚫 False Positive",
            "will_fix_later": "⏳ Will Fix Later"
        }
        
        for status, count in stats['by_status'].items():
            status_table.add_row(
                status_names.get(status, status.title()),
                str(count)
            )
        
        console.print("\n[bold magenta]📋 Status Breakdown[/bold magenta]")
        console.print(status_table)
    
    # Author activity (disabled for now)
    if False:  # stats.get('by_author'):
        author_table = Table(show_header=True, header_style="bold green", box=box.ROUNDED)
        author_table.add_column("Author", style="bold")
        author_table.add_column("Actions", style="cyan", justify="right")
        
        for author, count in sorted(stats['by_author'].items(), key=lambda x: x[1], reverse=True):
            author_table.add_row(author, str(count))
        
        console.print("\n[bold green]👥 Author Activity[/bold green]")
        console.print(author_table)
    
    return 0

def handle_feedback_search(feedback_tracker: FeedbackTracker, args) -> int:
    """Search findings by query"""
    if not args.query:
        console.print("[bold red]❌ --query required for search operation[/bold red]")
        return 1
    
    findings = feedback_tracker.search_findings(args.query)
    
    if not findings:
        console.print(f"[bold yellow]🔍 No findings match query: '{args.query}'[/bold yellow]")
        return 0
    
    console.print(f"[bold blue]🔍 Found {len(findings)} matching findings for: '{args.query}'[/bold blue]\n")
    
    # Use same display as list
    return handle_feedback_list(FeedbackTracker(), type('Args', (), {'status': None, 'author': None}))

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
    
    # Feedback system arguments
    parser.add_argument("--feedback", choices=["list", "show", "comment", "resolve", "false-positive", "will-fix-later", "stats", "search"], 
                       help="Feedback management operations")
    parser.add_argument("--finding-id", help="Finding ID for feedback operations")
    parser.add_argument("--message", help="Message for feedback operations")
    parser.add_argument("--author", help="Author name for feedback (defaults to system user)")
    parser.add_argument("--status", choices=["open", "resolve", "false_positive", "will_fix_later"], 
                       help="Filter findings by status")
    parser.add_argument("--query", help="Search query for findings")
    
    args = parser.parse_args()

    cfg = load_yaml(args.config) if os.path.exists(args.config) else {}
    rules = load_yaml(args.rules).get("guidelines", []) if os.path.exists(args.rules) else []
    formats = args.format or cfg.get("formats", ["md"])

    # Handle feedback operations first (separate from review workflow)
    if args.feedback:
        return handle_feedback_operations(args)
    
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

    # Initialize feedback tracker and annotate findings
    feedback_tracker = FeedbackTracker()
    
    # Import new findings for tracking
    imported_count = feedback_tracker.import_findings_for_tracking(findings)
    if imported_count > 0:
        console.print(f"[dim]📝 Imported {imported_count} new findings for tracking[/dim]")
    
    # Annotate findings with feedback data
    annotated_findings = feedback_tracker.annotate_findings(findings)
    
    out = {
        "summary": report.get("summary", ""),
        "effort": report.get("effort", "S"),
        "findings": annotated_findings,
        "mypy": mypy,
        "feedback_stats": feedback_tracker.get_finding_stats()
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
            severity = f.get('severity', 'info').upper()
            rule = f.get('rule', 'GEN')
            file_location = f.get('file', '?')
            line_num = f.get('line', '?')
            title = f.get('title', 'Unknown issue')
            description = f.get('description', 'No description available')
            recommendation = f.get('recommendation', 'No recommendation provided')
            
            md.append(f"- **{severity}** [{rule}] "
                      f"{file_location}:{line_num} — {title}\n"
                      f"  - {description}\n"
                      f"  - **Fix**: {recommendation}\n")
        Path("AI_REVIEW.md").write_text("\n".join(md))
        console.print("[bold green]💾 Wrote[/bold green] [cyan]AI_REVIEW.md[/cyan]")

    # Check for system issues in the review
    summary = out.get("summary", "")
    if "parse error" in summary.lower() or "non-json" in summary.lower():
        console.print(Panel(
            "[bold yellow]⚠️  AI Analysis Warning[/bold yellow]\n"
            f"Issue: {summary}\n\n"
            "[dim]Troubleshooting:[/dim]\n"
            "[dim]• Check that Ollama server is running: 'ollama serve'[/dim]\n"
            "[dim]• Verify model is available: 'ollama list'[/dim]\n"
            "[dim]• Try with smaller changes or simpler code[/dim]\n"
            "[dim]• Check .ai_review_cache/last_failed_response.txt for details[/dim]",
            border_style="yellow",
            box=box.ROUNDED
        ))
        console.print("")
    
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

    # Feedback statistics summary
    if out.get("feedback_stats"):
        feedback_stats = out["feedback_stats"]
        
        feedback_text = []
        feedback_text.append(f"[bold cyan]📊 Total Findings: {feedback_stats['total_findings']}[/bold cyan]")
        feedback_text.append(f"[dim]Active: {feedback_stats['active_findings']} | Comments: {feedback_stats['total_comments']}[/dim]")
        feedback_text.append(f"[bold green]Resolution Rate: {feedback_stats['resolution_rate']}%[/bold green]")
        
        # Status breakdown
        status_breakdown = []
        for status, count in feedback_stats['by_status'].items():
            if count > 0:
                status_display = status.replace('_', ' ').title()
                status_breakdown.append(f"{status_display}: {count}")
        
        if status_breakdown:
            feedback_text.append(f"[dim]{' | '.join(status_breakdown)}[/dim]")
        
        feedback_panel = Panel(
            "\n".join(feedback_text),
            title="[bold]💬 Feedback Summary[/bold]",
            border_style="cyan",
            box=box.ROUNDED
        )
        console.print(feedback_panel)
    
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
