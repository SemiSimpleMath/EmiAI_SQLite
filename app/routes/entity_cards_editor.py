"""
Entity Cards Editor Route
Flask blueprint for editing and managing entity cards
"""
from flask import Blueprint, render_template, request, jsonify
from app.models.base import get_session
from app.assistant.entity_management.entity_cards import (
    EntityCard,
    get_entity_card_by_name,
    search_entity_cards,
    get_entity_cards_by_type,
    get_most_used_entity_cards,
    get_entity_card_stats,
    create_entity_card,
    deactivate_entity_card
)
from sqlalchemy import func
import uuid
from datetime import datetime, timezone

entity_cards_editor_bp = Blueprint('entity_cards_editor', __name__)


class EntityCardManager:
    """Manager for entity card operations"""
    
    def __init__(self, session=None):
        self.session = session or get_session()
    
    def get_all_entity_cards(self, limit=100, offset=0, search_term=None, entity_type=None, sort_by='name'):
        """Get entity cards with filtering and sorting"""
        query = self.session.query(EntityCard).filter(EntityCard.is_active == True)
        
        # Apply search filter
        if search_term:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    EntityCard.entity_name.ilike(f'%{search_term}%'),
                    EntityCard.summary.ilike(f'%{search_term}%'),
                    EntityCard.entity_type.ilike(f'%{search_term}%')
                )
            )
        
        # Apply type filter
        if entity_type:
            query = query.filter(EntityCard.entity_type == entity_type)
        
        # Apply sorting
        if sort_by == 'name':
            query = query.order_by(EntityCard.entity_name.asc())
        elif sort_by == 'usage':
            query = query.order_by(EntityCard.usage_count.desc())
        elif sort_by == 'created':
            query = query.order_by(EntityCard.created_at.desc())
        elif sort_by == 'updated':
            query = query.order_by(EntityCard.updated_at.desc())
        
        total = query.count()
        cards = query.offset(offset).limit(limit).all()
        
        return {
            'cards': [self._card_to_dict(card) for card in cards],
            'total': total,
            'limit': limit,
            'offset': offset
        }
    
    def get_entity_card_by_id(self, card_id):
        """Get entity card by ID (SQLite uses string IDs)"""
        try:
            # For SQLite, IDs are stored as strings, so query with string directly
            card = self.session.query(EntityCard).filter(EntityCard.id == str(card_id)).first()
            if card:
                return {'success': True, 'card': self._card_to_dict(card)}
            return {'success': False, 'message': 'Entity card not found'}
        except Exception as e:
            return {'success': False, 'message': f'Error retrieving card: {str(e)}'}
    
    def create_entity_card(self, data):
        """Create a new entity card"""
        try:
            # Check if entity name already exists
            existing = get_entity_card_by_name(self.session, data.get('entity_name'))
            if existing:
                return {'success': False, 'message': f'Entity card with name "{data["entity_name"]}" already exists'}
            
            card = EntityCard(
                entity_name=data.get('entity_name'),
                entity_type=data.get('entity_type', 'unknown'),
                summary=data.get('summary', ''),
                key_facts=data.get('key_facts', []),
                relationships=data.get('relationships', []),
                aliases=data.get('aliases', []),
                original_description=data.get('original_description'),
                original_aliases=data.get('original_aliases', []),
                confidence=data.get('confidence'),
                source_node_id=str(data['source_node_id']) if data.get('source_node_id') else None,
                card_metadata=data.get('card_metadata', {})
            )
            
            self.session.add(card)
            self.session.commit()
            
            return {'success': True, 'card': self._card_to_dict(card)}
        except Exception as e:
            self.session.rollback()
            return {'success': False, 'message': f'Error creating entity card: {str(e)}'}
    
    def update_entity_card(self, card_id, data):
        """Update an existing entity card (SQLite uses string IDs)"""
        try:
            card = self.session.query(EntityCard).filter(EntityCard.id == str(card_id)).first()
            
            if not card:
                return {'success': False, 'message': 'Entity card not found'}
            
            # Update fields
            if 'entity_name' in data:
                # Check if new name conflicts with another card
                existing = get_entity_card_by_name(self.session, data['entity_name'])
                if existing and existing.id != card.id:
                    return {'success': False, 'message': f'Entity card with name "{data["entity_name"]}" already exists'}
                card.entity_name = data['entity_name']
            
            if 'entity_type' in data:
                card.entity_type = data['entity_type']
            if 'summary' in data:
                card.summary = data['summary']
            if 'key_facts' in data:
                card.key_facts = data['key_facts']
            if 'relationships' in data:
                card.relationships = data['relationships']
            if 'aliases' in data:
                card.aliases = data['aliases']
            if 'original_description' in data:
                card.original_description = data['original_description']
            if 'original_aliases' in data:
                card.original_aliases = data['original_aliases']
            if 'confidence' in data:
                card.confidence = data['confidence']
            if 'source_node_id' in data:
                card.source_node_id = str(data['source_node_id']) if data.get('source_node_id') else None
            if 'card_metadata' in data:
                card.card_metadata = data['card_metadata']
            
            card.updated_at = datetime.now(timezone.utc)
            self.session.commit()
            
            return {'success': True, 'card': self._card_to_dict(card)}
        except Exception as e:
            self.session.rollback()
            return {'success': False, 'message': f'Error updating entity card: {str(e)}'}
    
    def delete_entity_card(self, card_id):
        """Soft delete an entity card (SQLite uses string IDs)"""
        try:
            card = self.session.query(EntityCard).filter(EntityCard.id == str(card_id)).first()
            
            if not card:
                return {'success': False, 'message': 'Entity card not found'}
            
            card.is_active = False
            card.updated_at = datetime.now(timezone.utc)
            self.session.commit()
            
            return {'success': True, 'message': 'Entity card deleted successfully'}
        except Exception as e:
            self.session.rollback()
            return {'success': False, 'message': f'Error deleting entity card: {str(e)}'}
    
    def get_entity_types(self):
        """Get list of all entity types"""
        types = self.session.query(EntityCard.entity_type).filter(
            EntityCard.is_active == True
        ).distinct().all()
        return [t[0] for t in types]
    
    def _card_to_dict(self, card):
        """Convert EntityCard to dictionary"""
        return {
            'id': str(card.id),
            'entity_name': card.entity_name,
            'entity_type': card.entity_type,
            'summary': card.summary,
            'key_facts': card.key_facts or [],
            'relationships': card.relationships or [],
            'aliases': card.aliases or [],
            'original_description': card.original_description,
            'original_aliases': card.original_aliases or [],
            'confidence': card.confidence,
            'source_node_id': str(card.source_node_id) if card.source_node_id else None,
            'card_metadata': card.card_metadata or {},
            'is_active': card.is_active,
            'usage_count': card.usage_count,
            'last_used': card.last_used.isoformat() if card.last_used else None,
            'created_at': card.created_at.isoformat() if card.created_at else None,
            'updated_at': card.updated_at.isoformat() if card.updated_at else None
        }


def get_manager(session=None):
    """Get EntityCardManager instance with proper session handling"""
    if session is None:
        session = get_session()
    return EntityCardManager(session=session)


@entity_cards_editor_bp.route('/entity_cards', methods=['GET'])
def entity_cards_page():
    """Main entity cards editor page"""
    return render_template('entity_cards_editor.html')


@entity_cards_editor_bp.route('/api/entity_cards', methods=['GET'])
def api_get_entity_cards():
    """Get entity cards with filtering and pagination"""
    session = get_session()
    try:
        manager = get_manager(session=session)
        limit = request.args.get('limit', 50, type=int)
        offset = request.args.get('offset', 0, type=int)
        search_term = request.args.get('search', None)
        entity_type = request.args.get('type', None)
        sort_by = request.args.get('sort', 'name')
        
        result = manager.get_all_entity_cards(
            limit=limit,
            offset=offset,
            search_term=search_term,
            entity_type=entity_type,
            sort_by=sort_by
        )
        
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        session.close()


@entity_cards_editor_bp.route('/api/entity_cards/<card_id>', methods=['GET'])
def api_get_entity_card(card_id):
    """Get a specific entity card by ID"""
    print("I am at the route")
    session = get_session()
    try:
        manager = get_manager(session=session)
        result = manager.get_entity_card_by_id(card_id)
        if result['success']:
            return jsonify(result)
        return jsonify(result), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        session.close()


@entity_cards_editor_bp.route('/api/entity_cards', methods=['POST'])
def api_create_entity_card():
    """Create a new entity card"""
    session = get_session()
    try:
        manager = get_manager(session=session)
        data = request.get_json()
        result = manager.create_entity_card(data)
        if result['success']:
            return jsonify(result), 201
        return jsonify(result), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        session.close()


@entity_cards_editor_bp.route('/api/entity_cards/<card_id>', methods=['PUT'])
def api_update_entity_card(card_id):
    """Update an existing entity card"""
    session = get_session()
    try:
        manager = get_manager(session=session)
        data = request.get_json()
        result = manager.update_entity_card(card_id, data)
        if result['success']:
            return jsonify(result)
        return jsonify(result), 400
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        session.close()


@entity_cards_editor_bp.route('/api/entity_cards/<card_id>', methods=['DELETE'])
def api_delete_entity_card(card_id):
    """Delete an entity card"""
    session = get_session()
    try:
        manager = get_manager(session=session)
        result = manager.delete_entity_card(card_id)
        if result['success']:
            return jsonify(result)
        return jsonify(result), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        session.close()


@entity_cards_editor_bp.route('/api/entity_cards/stats', methods=['GET'])
def api_get_stats():
    """Get entity card statistics"""
    try:
        session = get_session()
        stats = get_entity_card_stats(session)
        session.close()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@entity_cards_editor_bp.route('/api/entity_cards/types', methods=['GET'])
def api_get_types():
    """Get list of all entity types"""
    session = get_session()
    try:
        manager = get_manager(session=session)
        types = manager.get_entity_types()
        return jsonify({'success': True, 'types': types})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500
    finally:
        session.close()

