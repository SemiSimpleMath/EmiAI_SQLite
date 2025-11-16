from flask import Blueprint, render_template, session, redirect, url_for
import uuid
index_route_bp = Blueprint('index', __name__)

@index_route_bp.route('/', methods=['GET', 'POST'])
def index():
    if 'user_id' not in session:
        session['user_id'] = str(uuid.uuid4())
    print("\nAt index route - redirecting to chatbot")
    # Redirect directly to chatbot instead of login
    return redirect(url_for('chat_bot.chat_bot'))

