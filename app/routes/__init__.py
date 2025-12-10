# this is the __init__ file for the routes.
from .index_route import index_route_bp
from .main import main_bp
from .chat_bot import chat_bot_bp
from .process_request import process_request_bp
from .process_audio import process_audio_bp
from .idle_route import idle_route_bp
from .render_repo_route import render_repo_route_bp
from .tool_route import tool_route_bp
from .agent_flow import agent_flow_route_bp
from .ask_user_route import ask_user_route_bp
from .daily_summary import daily_summary_route_bp
from .entity_cards_editor import entity_cards_editor_bp
from .google_oauth import google_oauth_bp
from .health_check import health_check_bp

# KG/Taxonomy/Graph Visualizer routes - only import if dependencies available (disabled in alpha)
# These all require sentence-transformers/chromadb which are not in alpha
try:
    from .kg_visualizer import kg_visualizer_bp
    from .taxonomy_viewer import taxonomy_viewer_bp
except ImportError as e:
    # sentence-transformers/chromadb not available - KG/Taxonomy features disabled
    kg_visualizer_bp = None
    taxonomy_viewer_bp = None
