# app/__init__.py
from flask import Flask
from flask_socketio import SocketIO
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from app.assistant.database.db_instance import db
from app.bootstrap import initialize_services

from app.assistant.utils.logging_config import get_logger
from app.socket_handlers import register_socket_handlers

logger = get_logger(__name__)

# Initialize SocketIO with threading
socketio = SocketIO(async_mode='threading')

def create_app(config_class="config.DevelopmentConfig"):
    app = Flask(__name__)
    app.config.from_object(config_class)
    CORS(app, supports_credentials=True)
    JWTManager(app)

    # No login required for this version
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
    db.init_app(app)

    with app.app_context():
        # Initialize database tables by feature group
        from app.database.table_initializer import initialize_all_tables
        initialize_all_tables()
        
        # Initialize services
        DI = initialize_services(app)

    app.DI = DI
    DI.socket_io = socketio

    register_socket_handlers(socketio)

    # Initialize event bus
    from app.assistant.initialize_system import initialize_system

    initialize_system()


# Import and register blueprints
    from .routes import (
        index_route_bp,
        main_bp,
        chat_bot_bp,
        process_request_bp,
        process_audio_bp,
        idle_route_bp,
        render_repo_route_bp,
        tool_route_bp,
        agent_flow_route_bp,
        ask_user_route_bp,
        daily_summary_route_bp,
        entity_cards_editor_bp,
        kg_visualizer_bp,
        taxonomy_viewer_bp,
        google_oauth_bp
    )
    
    # Import ngrok route
    from .routes.ngrok_route import ngrok_route_bp
    
    # Import user settings route
    from .routes.user_settings import user_settings_bp
    
    # Import setup wizard route
    from .routes.setup import setup_bp
    
    # Import preferences route
    from .routes.preferences import preferences_bp
    
    # Import graph visualizer API
    from .graph_visualizer.api import graph_api
    
    app.register_blueprint(index_route_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(chat_bot_bp)
    app.register_blueprint(process_request_bp)
    app.register_blueprint(process_audio_bp)
    app.register_blueprint(idle_route_bp)
    app.register_blueprint(render_repo_route_bp)
    app.register_blueprint(tool_route_bp)
    app.register_blueprint(agent_flow_route_bp)
    app.register_blueprint(ask_user_route_bp)
    app.register_blueprint(daily_summary_route_bp)
    app.register_blueprint(entity_cards_editor_bp)
    app.register_blueprint(kg_visualizer_bp)
    app.register_blueprint(taxonomy_viewer_bp)
    app.register_blueprint(google_oauth_bp)
    app.register_blueprint(ngrok_route_bp)
    app.register_blueprint(user_settings_bp)
    app.register_blueprint(setup_bp)
    app.register_blueprint(preferences_bp)
    
    # Register graph visualizer API
    app.register_blueprint(graph_api)

    return app, socketio