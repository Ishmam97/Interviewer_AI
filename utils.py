import os
import json
from typing import Dict, Any, List, Optional
from datetime import datetime


def validate_file_paths(*file_paths: str) -> bool:
    """Validate that all provided file paths exist"""
    for path in file_paths:
        if not os.path.exists(path):
            print(f"❌ File not found: {path}")
            return False
    return True


def save_interview_session(state: Dict[str, Any], output_dir: str = "./interview_sessions") -> str:
    """Save interview session to JSON file"""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"interview_session_{timestamp}.json"
    filepath = os.path.join(output_dir, filename)
    
    # Convert state to JSON-serializable format
    serializable_state = _make_json_serializable(state)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(serializable_state, f, indent=2, ensure_ascii=False)
    
    print(f"📁 Interview session saved to: {filepath}")
    return filepath


def load_interview_session(filepath: str) -> Dict[str, Any]:
    """Load interview session from JSON file"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def _make_json_serializable(obj: Any) -> Any:
    """Make an object JSON serializable"""
    if isinstance(obj, dict):
        return {key: _make_json_serializable(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_make_json_serializable(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool)) or obj is None:
        return obj
    else:
        return str(obj)


def format_score_distribution(interview_notes: List[Dict[str, Any]]) -> str:
    """Format score distribution for display"""
    if not interview_notes:
        return "No scores available"
    
    scores = [note.get('score', 0) for note in interview_notes]
    score_counts = {}
    
    for score in scores:
        score_counts[score] = score_counts.get(score, 0) + 1
    
    result = "Score Distribution:\n"
    for score in sorted(score_counts.keys(), reverse=True):
        count = score_counts[score]
        bar = "█" * count
        result += f"{score}/10: {bar} ({count})\n"
    
    return result


def format_category_breakdown(interview_notes: List[Dict[str, Any]]) -> str:
    """Format category breakdown for display"""
    if not interview_notes:
        return "No categories available"
    
    categories = {}
    for note in interview_notes:
        category = note.get('question_category', 'general')
        if category not in categories:
            categories[category] = {'count': 0, 'total_score': 0}
        
        categories[category]['count'] += 1
        categories[category]['total_score'] += note.get('score', 0)
    
    result = "Category Breakdown:\n"
    for category, data in categories.items():
        avg_score = data['total_score'] / data['count'] if data['count'] > 0 else 0
        result += f"{category.title()}: {data['count']} questions, avg score: {avg_score:.1f}/10\n"
    
    return result


def print_interview_summary(state: Dict[str, Any]) -> None:
    """Print a formatted interview summary"""
    print("\n" + "="*60)
    print("INTERVIEW SUMMARY")
    print("="*60)
    
    interview_notes = state.get('interview_notes', [])
    
    if not interview_notes:
        print("No interview data available.")
        return
    
    # Basic stats
    total_questions = len(interview_notes)
    scores = [note.get('score', 0) for note in interview_notes]
    avg_score = sum(scores) / len(scores) if scores else 0
    
    print(f"Total Questions: {total_questions}")
    print(f"Average Score: {avg_score:.1f}/10")
    print(f"Highest Score: {max(scores) if scores else 0}/10")
    print(f"Lowest Score: {min(scores) if scores else 0}/10")
    
    print("\n" + format_score_distribution(interview_notes))
    print(format_category_breakdown(interview_notes))


def export_report_to_file(report: str, output_dir: str = "./reports") -> str:
    """Export interview report to a text file"""
    os.makedirs(output_dir, exist_ok=True)
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"interview_report_{timestamp}.txt"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("INTERVIEW REPORT\n")
        f.write("=" * 50 + "\n")
        f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(report)
    
    print(f"📄 Report exported to: {filepath}")
    return filepath


def clean_old_files(directory: str, max_age_days: int = 30) -> None:
    """Clean old files from a directory"""
    if not os.path.exists(directory):
        return
    
    current_time = datetime.now()
    deleted_count = 0
    
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        
        if os.path.isfile(filepath):
            file_time = datetime.fromtimestamp(os.path.getctime(filepath))
            age_days = (current_time - file_time).days
            
            if age_days > max_age_days:
                os.remove(filepath)
                deleted_count += 1
    
    if deleted_count > 0:
        print(f"🧹 Cleaned {deleted_count} old files from {directory}")


def validate_openai_key(api_key: str) -> bool:
    """Basic validation for OpenAI API key format"""
    if not api_key:
        return False
    
    # Basic format check (OpenAI keys typically start with 'sk-')
    if not api_key.startswith('sk-'):
        return False
    
    # Check length (OpenAI keys are usually 51 characters)
    if len(api_key) < 40:
        return False
    
    return True