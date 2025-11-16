from flask import Blueprint, render_template, make_response

graph_visualizer_bp = Blueprint('graph_visualizer', __name__, 
                                template_folder='../graph_visualizer/templates')

@graph_visualizer_bp.route('/graph')
def graph_visualizer():
    """Serve the graph visualizer page"""
    response = make_response(render_template('graph_visualizer.html'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response




