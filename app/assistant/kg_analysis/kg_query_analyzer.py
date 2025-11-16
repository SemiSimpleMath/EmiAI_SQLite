"""
Knowledge Graph Query Analyzer

This utility provides analysis and insights about KG queries made by agents.
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from collections import Counter, defaultdict
import re

from app.assistant.utils.logging_config import get_logger

logger = get_logger(__name__)


class KGQueryAnalyzer:
    """
    Analyzes KG query logs to provide insights about agent behavior and query patterns.
    """
    
    def __init__(self, log_file_path: str = "app/assistant/logs/kg_query_log.jsonl"):
        self.log_file_path = log_file_path
        self.queries = []
        self._load_queries()
    
    def _load_queries(self):
        """Load queries from the log file."""
        if not os.path.exists(self.log_file_path):
            logger.warning(f"KG query log file not found: {self.log_file_path}")
            return
        
        try:
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        try:
                            entry = json.loads(line.strip())
                            self.queries.append(entry)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse log entry: {line.strip()}")
        except Exception as e:
            logger.error(f"Failed to load KG query log: {e}")
    
    def get_basic_statistics(self) -> Dict[str, Any]:
        """Get basic statistics about KG queries."""
        if not self.queries:
            return {
                'total_entries': 0,
                'total_queries': 0,
                'successful_queries': 0,
                'failed_queries': 0,
                'success_rate': 0.0,
                'date_range': None
            }
        
        total_entries = len(self.queries)
        started_queries = [q for q in self.queries if q.get('event') == 'kg_query_started']
        completed_queries = [q for q in self.queries if q.get('event') == 'kg_query_completed']
        error_queries = [q for q in self.queries if q.get('event') == 'kg_query_error']
        
        success_rate = (len(completed_queries) / len(started_queries) * 100) if started_queries else 0
        
        # Get date range
        timestamps = [q.get('timestamp') for q in self.queries if q.get('timestamp')]
        if timestamps:
            try:
                dates = [datetime.fromisoformat(ts.replace('Z', '+00:00')) for ts in timestamps]
                date_range = {
                    'start': min(dates).isoformat(),
                    'end': max(dates).isoformat(),
                    'duration_days': (max(dates) - min(dates)).days
                }
            except:
                date_range = None
        else:
            date_range = None
        
        return {
            'total_entries': total_entries,
            'total_queries': len(started_queries),
            'successful_queries': len(completed_queries),
            'failed_queries': len(error_queries),
            'success_rate': round(success_rate, 2),
            'date_range': date_range
        }
    
    def analyze_question_patterns(self) -> Dict[str, Any]:
        """Analyze patterns in the questions being asked."""
        questions = []
        for query in self.queries:
            if query.get('event') == 'kg_query_started':
                # Use task field (current standard), fall back to question for backward compatibility
                task_text = query.get('task', '')
                if task_text:
                    questions.append(task_text)
                else:
                    # Fallback for older entries that used 'question' field
                    question_text = query.get('question', '')
                    if question_text:
                        questions.append(question_text)
        
        if not questions:
            return {
                'total_questions': 0,
                'common_words': [],
                'question_types': [],
                'average_length': 0
            }
        
        # Analyze question length
        lengths = [len(q) for q in questions]
        avg_length = sum(lengths) / len(lengths)
        
        # Extract common words
        all_words = []
        for question in questions:
            words = re.findall(r'\b\w+\b', question.lower())
            all_words.extend(words)
        
        word_counts = Counter(all_words)
        common_words = word_counts.most_common(20)
        
        # Categorize question types
        question_types = self._categorize_questions(questions)
        
        return {
            'total_questions': len(questions),
            'common_words': common_words,
            'question_types': question_types,
            'average_length': round(avg_length, 1),
            'length_distribution': {
                'short': len([l for l in lengths if l < 50]),
                'medium': len([l for l in lengths if 50 <= l < 100]),
                'long': len([l for l in lengths if l >= 100])
            }
        }
    
    def _categorize_questions(self, questions: List[str]) -> Dict[str, int]:
        """Categorize questions by type."""
        categories = {
            'who': 0,
            'what': 0,
            'when': 0,
            'where': 0,
            'why': 0,
            'how': 0,
            'relationship': 0,
            'property': 0,
            'other': 0
        }
        
        for question in questions:
            question_lower = question.lower()
            
            if question_lower.startswith('who'):
                categories['who'] += 1
            elif question_lower.startswith('what'):
                categories['what'] += 1
            elif question_lower.startswith('when'):
                categories['when'] += 1
            elif question_lower.startswith('where'):
                categories['where'] += 1
            elif question_lower.startswith('why'):
                categories['why'] += 1
            elif question_lower.startswith('how'):
                categories['how'] += 1
            elif any(word in question_lower for word in ['relationship', 'related', 'connected', 'link']):
                categories['relationship'] += 1
            elif any(word in question_lower for word in ['property', 'attribute', 'has', 'owns', 'belongs']):
                categories['property'] += 1
            else:
                categories['other'] += 1
        
        return categories
    
    def analyze_result_patterns(self) -> Dict[str, Any]:
        """Analyze patterns in the results returned."""
        results = []
        for query in self.queries:
            if query.get('event') == 'kg_query_completed':
                results.append(query)
        
        if not results:
            return {
                'total_results': 0,
                'result_types': {},
                'content_lengths': {},
                'empty_results': 0
            }
        
        # Analyze result types
        result_types = Counter([r.get('result_type', 'unknown') for r in results])
        
        # Analyze content lengths
        content_lengths = [len(r.get('result_content', '')) for r in results]
        empty_results = len([l for l in content_lengths if l == 0])
        
        return {
            'total_results': len(results),
            'result_types': dict(result_types),
            'content_lengths': {
                'average': round(sum(content_lengths) / len(content_lengths), 1),
                'min': min(content_lengths),
                'max': max(content_lengths),
                'empty': empty_results,
                'non_empty': len(content_lengths) - empty_results
            }
        }
    
    def get_recent_queries(self, hours: int = 24) -> List[Dict[str, Any]]:
        """Get queries from the last N hours."""
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        recent_queries = []
        for query in self.queries:
            if query.get('timestamp'):
                try:
                    query_time = datetime.fromisoformat(query['timestamp'].replace('Z', '+00:00'))
                    if query_time >= cutoff_time:
                        recent_queries.append(query)
                except:
                    continue
        
        return recent_queries
    
    def get_query_by_id(self, query_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific query by ID."""
        for query in self.queries:
            if query.get('query_id') == query_id:
                return query
        return None
    
    def get_failed_queries(self) -> List[Dict[str, Any]]:
        """Get all failed queries."""
        return [q for q in self.queries if q.get('event') == 'kg_query_error']
    
    def get_successful_queries(self) -> List[Dict[str, Any]]:
        """Get all successful queries."""
        return [q for q in self.queries if q.get('event') == 'kg_query_completed']
    
    def export_analysis_report(self, output_file: str = "kg_query_analysis_report.json"):
        """Export a comprehensive analysis report."""
        report = {
            'generated_at': datetime.now().isoformat(),
            'log_file': self.log_file_path,
            'basic_statistics': self.get_basic_statistics(),
            'question_patterns': self.analyze_question_patterns(),
            'result_patterns': self.analyze_result_patterns(),
            'recent_queries_24h': len(self.get_recent_queries(24)),
            'failed_queries_count': len(self.get_failed_queries()),
            'successful_queries_count': len(self.get_successful_queries())
        }
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, ensure_ascii=False)
            logger.info(f"Analysis report exported to: {output_file}")
            return output_file
        except Exception as e:
            logger.error(f"Failed to export analysis report: {e}")
            return None
    
    def print_summary(self):
        """Print a summary of the analysis."""
        stats = self.get_basic_statistics()
        question_patterns = self.analyze_question_patterns()
        result_patterns = self.analyze_result_patterns()
        
        print("🔍 Knowledge Graph Query Analysis Summary")
        print("=" * 50)
        print(f"📊 Total Queries: {stats['total_queries']}")
        print(f"✅ Successful: {stats['successful_queries']}")
        print(f"❌ Failed: {stats['failed_queries']}")
        print(f"📈 Success Rate: {stats['success_rate']}%")
        
        if stats['date_range']:
            print(f"📅 Date Range: {stats['date_range']['start']} to {stats['date_range']['end']}")
            print(f"⏱️ Duration: {stats['date_range']['duration_days']} days")
        
        print(f"\n📝 Question Analysis:")
        print(f"   Average Length: {question_patterns['average_length']} characters")
        print(f"   Question Types: {dict(question_patterns['question_types'])}")
        
        print(f"\n📋 Result Analysis:")
        print(f"   Result Types: {result_patterns['result_types']}")
        if result_patterns['content_lengths']['non_empty'] > 0:
            print(f"   Average Content Length: {result_patterns['content_lengths']['average']} characters")
            print(f"   Empty Results: {result_patterns['content_lengths']['empty']}")
        
        print(f"\n🔍 Recent Activity (24h): {len(self.get_recent_queries(24))} queries")


def main():
    """Main function to run the analyzer."""
    analyzer = KGQueryAnalyzer()
    analyzer.print_summary()
    
    # Export report
    report_file = analyzer.export_analysis_report()
    if report_file:
        print(f"\n📄 Detailed report exported to: {report_file}")


if __name__ == "__main__":
    main()
