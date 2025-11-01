import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

class FeedbackStatus(Enum):
    """Possible feedback statuses for findings"""
    OPEN = "open"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive" 
    ACKNOWLEDGED = "acknowledged"
    WILL_FIX_LATER = "will_fix_later"
    IN_PROGRESS = "in_progress"

@dataclass
class FeedbackEntry:
    """Represents a single feedback entry"""
    timestamp: str
    author: str
    action: str  # "comment", "status_change", "created"
    message: str
    status: Optional[str] = None

@dataclass
class FindingFeedback:
    """Complete feedback record for a finding"""
    finding_id: str
    file: str
    line: int
    rule: str
    title: str
    status: str = FeedbackStatus.OPEN.value
    entries: List[FeedbackEntry] = None
    created_at: str = None
    updated_at: str = None
    
    def __post_init__(self):
        if self.entries is None:
            self.entries = []
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()
        if self.updated_at is None:
            self.updated_at = self.created_at

class FeedbackTracker:
    """Manages feedback and discussions for code review findings"""
    
    def __init__(self, feedback_file: str = ".ai_review_feedback.json"):
        self.feedback_file = Path(feedback_file)
        self.feedback_data: Dict[str, FindingFeedback] = {}
        self.load_feedback()
    
    def generate_finding_id(self, finding: Dict[str, Any]) -> str:
        """Generate a consistent ID for a finding"""
        # Create ID from file, line, rule, and title hash
        content = f"{finding.get('file', '')}{finding.get('line', 0)}{finding.get('rule', '')}{finding.get('title', '')}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def load_feedback(self):
        """Load existing feedback from file"""
        if not self.feedback_file.exists():
            return
            
        try:
            with open(self.feedback_file, 'r') as f:
                data = json.load(f)
                
            for finding_id, feedback_dict in data.items():
                # Convert entries back to FeedbackEntry objects
                entries = [FeedbackEntry(**entry) for entry in feedback_dict.get('entries', [])]
                feedback_dict['entries'] = entries
                
                self.feedback_data[finding_id] = FindingFeedback(**feedback_dict)
                
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            print(f"⚠️  Warning: Could not load feedback data: {e}")
    
    def save_feedback(self):
        """Save feedback data to file"""
        try:
            # Convert to serializable format
            data = {}
            for finding_id, feedback in self.feedback_data.items():
                feedback_dict = asdict(feedback)
                data[finding_id] = feedback_dict
                
            with open(self.feedback_file, 'w') as f:
                json.dump(data, f, indent=2)
                
        except Exception as e:
            print(f"⚠️  Warning: Could not save feedback data: {e}")
    
    def add_feedback(self, finding_id: str, action: str, message: str = "", 
                    author: str = "developer", status: str = None) -> bool:
        """Add feedback entry to a finding"""
        if finding_id not in self.feedback_data:
            return False
            
        entry = FeedbackEntry(
            timestamp=datetime.now().isoformat(),
            author=author,
            action=action,
            message=message,
            status=status
        )
        
        feedback = self.feedback_data[finding_id]
        feedback.entries.append(entry)
        feedback.updated_at = entry.timestamp
        
        if status:
            feedback.status = status
            
        self.save_feedback()
        return True
    
    def create_finding_feedback(self, finding: Dict[str, Any]) -> str:
        """Create feedback record for a new finding"""
        finding_id = self.generate_finding_id(finding)
        
        if finding_id not in self.feedback_data:
            feedback = FindingFeedback(
                finding_id=finding_id,
                file=finding.get('file', ''),
                line=finding.get('line', 0),
                rule=finding.get('rule', ''),
                title=finding.get('title', ''),
                status=FeedbackStatus.OPEN.value
            )
            
            # Add creation entry
            feedback.entries.append(FeedbackEntry(
                timestamp=feedback.created_at,
                author="system",
                action="created",
                message=f"Finding created: {finding.get('title', 'Unknown issue')}"
            ))
            
            self.feedback_data[finding_id] = feedback
            self.save_feedback()
            
        return finding_id
    
    def mark_resolved(self, finding_id: str, comment: str = "", author: str = "developer") -> bool:
        """Mark a finding as resolved"""
        return self.change_status(finding_id, FeedbackStatus.RESOLVED.value, comment, author)
    
    def mark_false_positive(self, finding_id: str, comment: str = "", author: str = "developer") -> bool:
        """Mark a finding as false positive"""
        return self.change_status(finding_id, FeedbackStatus.FALSE_POSITIVE.value, comment, author)
    
    def change_status(self, finding_id: str, status: str, comment: str = "", author: str = "developer") -> bool:
        """Change status of a finding"""
        if finding_id not in self.feedback_data:
            return False
            
        message = f"Status changed to {status}"
        if comment:
            message += f": {comment}"
            
        return self.add_feedback(finding_id, "status_change", message, author, status)
    
    def add_comment(self, finding_id: str, comment: str, author: str = "developer") -> bool:
        """Add a comment to a finding"""
        return self.add_feedback(finding_id, "comment", comment, author)
    
    def get_finding_feedback(self, finding_id: str) -> Optional[FindingFeedback]:
        """Get feedback for a specific finding"""
        return self.feedback_data.get(finding_id)
    
    def get_all_feedback(self) -> Dict[str, FindingFeedback]:
        """Get all feedback data"""
        return self.feedback_data
    
    def filter_by_status(self, status: str) -> List[FindingFeedback]:
        """Get all findings with specific status"""
        return [feedback for feedback in self.feedback_data.values() 
                if feedback.status == status]
    
    def get_statistics(self) -> Dict[str, int]:
        """Get feedback statistics"""
        stats = {}
        for status in FeedbackStatus:
            stats[status.value] = len(self.filter_by_status(status.value))
        return stats
    
    def annotate_findings(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Add feedback information to findings"""
        annotated_findings = []
        
        for finding in findings:
            finding_id = self.generate_finding_id(finding)
            
            # Create feedback record if it doesn't exist
            if finding_id not in self.feedback_data:
                self.create_finding_feedback(finding)
            
            # Add feedback info to finding
            annotated_finding = finding.copy()
            feedback = self.feedback_data[finding_id]
            
            annotated_finding.update({
                "finding_id": finding_id,
                "feedback_status": feedback.status,
                "feedback_count": len(feedback.entries),
                "last_updated": feedback.updated_at
            })
            
            annotated_findings.append(annotated_finding)
            
        return annotated_findings
    
    def search_findings(self, query: str) -> List[FindingFeedback]:
        """Search findings by file, rule, or title"""
        query = query.lower()
        results = []
        
        for feedback in self.feedback_data.values():
            if (query in feedback.file.lower() or 
                query in feedback.rule.lower() or 
                query in feedback.title.lower()):
                results.append(feedback)
                
        return results
    
    def list_findings(self, status: str = None, author: str = None) -> Dict[str, Dict]:
        """List findings with optional filtering"""
        results = {}
        
        for finding_id, feedback in self.feedback_data.items():
            # Filter by status if provided
            if status and feedback.status != status:
                continue
            
            # Filter by author if provided (check entries)
            if author:
                author_found = False
                for entry in feedback.entries:
                    if entry.author == author:
                        author_found = True
                        break
                if not author_found:
                    continue
            
            # Convert to dict format for display
            results[finding_id] = {
                "status": feedback.status,
                "file": feedback.file,
                "line": feedback.line,
                "rule": feedback.rule,
                "title": feedback.title,
                "discussion": feedback.entries,
                "created_at": feedback.created_at,
                "updated_at": feedback.updated_at
            }
            
        return results
    
    def mark_will_fix_later(self, finding_id: str, comment: str = "", author: str = "developer") -> bool:
        """Mark a finding as will fix later"""
        return self.change_status(finding_id, FeedbackStatus.WILL_FIX_LATER.value, comment, author)
    
    def get_finding_stats(self) -> Dict[str, Any]:
        """Get comprehensive feedback statistics"""
        stats = self.get_statistics()
        
        # Add additional stats
        total_findings = len(self.feedback_data)
        total_comments = sum(len(feedback.entries) for feedback in self.feedback_data.values())
        
        # Calculate resolution rate
        resolved_count = stats.get(FeedbackStatus.RESOLVED.value, 0)
        false_positive_count = stats.get(FeedbackStatus.FALSE_POSITIVE.value, 0)
        resolution_rate = 0
        if total_findings > 0:
            resolution_rate = ((resolved_count + false_positive_count) / total_findings) * 100
        
        return {
            "total_findings": total_findings,
            "total_comments": total_comments,
            "resolution_rate": round(resolution_rate, 1),
            "by_status": stats,
            "active_findings": total_findings - resolved_count - false_positive_count
        }
    
    def import_findings_for_tracking(self, findings: List[Dict[str, Any]]) -> int:
        """Import findings and create feedback records for new ones"""
        imported_count = 0
        
        for finding in findings:
            finding_id = self.create_finding_feedback(finding)
            if finding_id not in self.feedback_data:
                imported_count += 1
                
        return imported_count