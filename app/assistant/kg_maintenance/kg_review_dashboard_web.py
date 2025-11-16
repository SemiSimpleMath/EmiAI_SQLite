#!/usr/bin/env python3
"""
KG Review Dashboard Web Interface

Flask web application for reviewing KG findings from multiple sources:
- Repair pipeline suggestions
- Explorer findings  
- Maintenance issues

Allows bulk review, annotation, and execution of approved changes.
"""
import app.assistant.tests.test_setup  # Initialize services
import json
import sys
from datetime import datetime
from typing import List, Dict, Any

from flask import Flask, render_template, request, jsonify, redirect, url_for

from app.assistant.kg_review.review_manager import KGReviewManager
from app.assistant.kg_review.data_models.kg_review import (
    ReviewSource, ReviewStatus, ReviewPriority, FindingType
)

app = Flask(__name__, template_folder='app/assistant/kg_review/web/templates')
app.secret_key = 'kg_review_dashboard_secret_2024'

# Global manager instance
review_manager = KGReviewManager()


@app.route('/')
def index():
    """Main dashboard page"""
    return render_template('kg_review_dashboard.html')


@app.route('/api/stats')
def api_stats():
    """Get statistics about reviews"""
    try:
        stats = review_manager.get_stats()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/reviews')
def api_get_reviews():
    """Get reviews with optional filtering and fresh node context"""
    try:
        from app.assistant.kg_repair_pipeline.utils.kg_operations import KGOperations
        
        status = request.args.get('status')
        source = request.args.get('source')
        priority = request.args.get('priority')
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
        
        reviews = review_manager.get_reviews(
            status=status,
            source=source,
            priority=priority,
            limit=limit,
            offset=offset
        )
        
        kg_ops = KGOperations()
        enriched_reviews = []
        
        for review in reviews:
            review_dict = review.to_dict()
            
            # Fetch fresh node data from KG
            try:
                current_node_info = kg_ops.get_node_info(str(review.node_id))
                
                if current_node_info:
                    # Extract fresh context
                    fresh_context = {
                        'description': current_node_info.get('description'),
                        'start_date': current_node_info.get('start_date'),
                        'end_date': current_node_info.get('end_date'),
                        'start_date_confidence': current_node_info.get('start_date_confidence'),
                        'end_date_confidence': current_node_info.get('end_date_confidence'),
                        'valid_during': current_node_info.get('valid_during'),
                        'status': current_node_info.get('status'),
                        'edges_summary': []
                    }
                    
                    # Extract edge information with sentences
                    if 'connections' in current_node_info:
                        for edge in current_node_info['connections'][:5]:
                            connected = edge.get('connected_node', {})
                            fresh_context['edges_summary'].append({
                                'relationship': edge.get('edge_type', 'connected'),
                                'target': connected.get('label', 'unknown'),
                                'sentence': edge.get('sentence', '')
                            })
                        print(f"✅ Fetched {len(fresh_context['edges_summary'])} edges for node {review.node_id}")
                    
                    # Replace context_data with fresh data
                    review_dict['context_data'] = fresh_context
                else:
                    print(f"⚠️ No node info returned for {review.node_id}")
                    
            except Exception as e:
                import traceback
                print(f"❌ Warning: Could not fetch fresh data for node {review.node_id}: {e}")
                print(f"   Traceback: {traceback.format_exc()}")
                # Keep existing context_data if fetch fails
            
            enriched_reviews.append(review_dict)
        
        return jsonify({
            'success': True,
            'reviews': enriched_reviews,
            'count': len(enriched_reviews)
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/review/<review_id>')
def api_get_review(review_id):
    """Get a single review"""
    try:
        review = review_manager.get_review(review_id)
        if not review:
            return jsonify({'success': False, 'error': 'Review not found'}), 404
        
        return jsonify({'success': True, 'review': review.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/review/<review_id>', methods=['PUT'])
def api_update_review(review_id):
    """Update a review"""
    try:
        data = request.get_json()
        
        review = review_manager.update_review(
            review_id=review_id,
            status=data.get('status'),
            priority=data.get('priority'),
            user_notes=data.get('user_notes'),
            user_instructions=data.get('user_instructions'),
            reviewed_by=data.get('reviewed_by'),
            is_false_positive=data.get('is_false_positive')
        )
        
        if not review:
            return jsonify({'success': False, 'error': 'Review not found'}), 404
        
        return jsonify({'success': True, 'review': review.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/review/<review_id>/approve', methods=['POST'])
def api_approve_review(review_id):
    """Approve a review for implementation"""
    try:
        data = request.get_json() or {}
        user_instructions = data.get('user_instructions')
        reviewed_by = data.get('reviewed_by', 'user')
        
        # Update with instructions if provided
        if user_instructions:
            review_manager.update_review(
                review_id=review_id,
                user_instructions=user_instructions
            )
        
        # Approve
        review = review_manager.update_review(
            review_id=review_id,
            status='approved',
            reviewed_by=reviewed_by
        )
        
        if not review:
            return jsonify({'success': False, 'error': 'Review not found'}), 404
        
        return jsonify({'success': True, 'review': review.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/review/<review_id>/reject', methods=['POST'])
def api_reject_review(review_id):
    """Reject a review"""
    try:
        data = request.get_json() or {}
        reviewed_by = data.get('reviewed_by', 'user')
        is_false_positive = data.get('is_false_positive', False)
        
        review = review_manager.update_review(
            review_id=review_id,
            status='rejected',
            reviewed_by=reviewed_by,
            is_false_positive=is_false_positive
        )
        
        if not review:
            return jsonify({'success': False, 'error': 'Review not found'}), 404
        
        return jsonify({'success': True, 'review': review.to_dict()})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/review/<review_id>/execute', methods=['POST'])
def api_execute_review(review_id):
    """Execute a single approved review"""
    try:
        result = review_manager.execute_review(review_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/batch/approve', methods=['POST'])
def api_batch_approve():
    """Approve multiple reviews"""
    try:
        data = request.get_json()
        review_ids = data.get('review_ids', [])
        reviewed_by = data.get('reviewed_by', 'user')
        
        results = []
        for review_id in review_ids:
            review = review_manager.update_review(
                review_id=review_id,
                status='approved',
                reviewed_by=reviewed_by
            )
            results.append({
                'review_id': review_id,
                'success': review is not None
            })
        
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/batch/reject', methods=['POST'])
def api_batch_reject():
    """Reject multiple reviews"""
    try:
        data = request.get_json()
        review_ids = data.get('review_ids', [])
        reviewed_by = data.get('reviewed_by', 'user')
        
        results = []
        for review_id in review_ids:
            review = review_manager.update_review(
                review_id=review_id,
                status='rejected',
                reviewed_by=reviewed_by
            )
            results.append({
                'review_id': review_id,
                'success': review is not None
            })
        
        return jsonify({'success': True, 'results': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/batch/execute', methods=['POST'])
def api_batch_execute():
    """Execute multiple approved reviews"""
    try:
        data = request.get_json()
        review_ids = data.get('review_ids', [])
        
        if not review_ids:
            return jsonify({'success': False, 'error': 'No review IDs provided'}), 400
        
        result = review_manager.execute_batch(review_ids)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/export', methods=['GET'])
def api_export():
    """Export reviews to JSON"""
    try:
        status = request.args.get('status')
        source = request.args.get('source')
        
        reviews = review_manager.get_reviews(status=status, source=source, limit=1000)
        
        export_data = {
            'exported_at': datetime.now().isoformat(),
            'filters': {
                'status': status,
                'source': source
            },
            'count': len(reviews),
            'reviews': [review.to_dict() for review in reviews]
        }
        
        return jsonify({'success': True, 'data': export_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("🌐 Starting KG Review Dashboard...")
    print("📱 Open your browser and go to: http://localhost:5002")
    print("\n📊 Dashboard features:")
    print("  - Review KG findings from multiple sources")
    print("  - Add notes and implementation instructions")
    print("  - Approve/reject reviews")
    print("  - Execute approved changes in batch")
    app.run(debug=True, port=5002, host='0.0.0.0', use_reloader=False)

