from flask import Flask, request, jsonify, render_template, session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv
import anthropic
from flask_sqlalchemy import SQLAlchemy
import secrets
import os

load_dotenv()

app = Flask(__name__)

def get_real_ip():
    forwarded = request.headers.get('X-Forwarded-For')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.remote_addr

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=['200 per day', '50 per hour', '5 per minute'],
    storage_uri='memory://'
)
app.secret_key = os.getenv('SECRET_KEY')

database_url = os.getenv('DATABASE_URL', 'sqlite:///chat.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://','postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = os.getenv('RENDER') is not None
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

db= SQLAlchemy(app)

class message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50))
    role = db.Column(db.String(10))
    content = db.Column(db.Text)

with app.app_context():
    db.create_all()

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

system_prompt = """YYou are a helpful assistant for Bloom bakery.
    Bakery information:
    - List of items sold with their costs;
    Cupcakes: Vanilla Dream — $2.99, Chocolate Bliss — $3.49, Strawberry Cloud — $3.49
    Cakes: Classic Cheesecake — $24.99, Chocolate Fudge — $28.99, Red Velvet — $26.99
    Pastries: Glazed Donuts (6 pcs) — $4.99, Cinnamon Roll — $3.99, Butter Croissant — $2.99
    Drinks: Iced Latte — $4.49, Strawberry Milkshake — $5.99, Hot Chocolate — $3.99
    - hours:  Mon - Fri: 7AM - 8PM and Sat - Sun: 8AM - 9PM
    - Location:  142 Rosewood Avenue, Brooklyn, New York, NY 11201
    - Phone: +1 (718) 555-0192 
    Answer questions helpfully and professionally. If the user asks about something you do not have enough information on, politely answer that you do not know and guide her to other ways you can offer help.
    If the message is long, organize it nicely, use bullet points or emojis if necessary. If asked something unrelated to bakery, politely redirect. DO NOT ENGAGE IN ANY CONVERSATION UNRELATED TO THE BAKERY. Refer to the user as 'Bestie'. 
    Have a friendly personality, use emojis in your texts, you are also encouraged to use playful remarks without insulting someone or hurting their feelings. Do not overuse asterisks or bullet points, start a new line for better readability while listing menu ingredients."""


@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
@limiter.limit('5 per minute')
def chat():
    print(f"Real IP: {get_real_ip()}")  
    print(f"X-Forwarded-For header: {request.headers.get('X-Forwarded-For')}")
    if 'session_id' not in session:
        session['session_id']=secrets.token_hex(8)
    session_id = session['session_id']

    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'error':'Please send a message'}), 400

    if len(user_message)>2000:
        return jsonify({'error':'Message too long (max 2000 characters)'}), 400


    db.session.add(message(session_id=session_id, role='user', content=user_message))
    db.session.commit()

    history = message.query.filter_by(session_id=session_id).order_by(message.id.desc()).limit(10).all()
    history = history[::-1] 

    claude_messages = [
        {'role':'user' if m.role == 'user' else 'assistant', 'content':m.content}
        for m in history
    ]

    try:
        response = client.messages.create(
        model='claude-haiku-4-5-20251001',
        max_tokens=300,
        system=system_prompt,
        messages=claude_messages
        )
        if not response.content or not response.content[0].text:
            return jsonify({'error': 'No response generated, please rephrase.'}), 500
        reply = response.content[0].text
    except anthropic.APIConnectionError:
        return jsonify({'error': 'Cannot reach the AI service. Please try again.'}), 503
    except anthropic.RateLimitError:
        return jsonify({'error': 'Too many requests. Please wait a moment.'}), 429
    except anthropic.APIStatusError as e:
        print(f"Anthropic API error: {e.status_code} - {e.message}")
        return jsonify({'error': 'AI service error. Please try again.'}), 503
    except Exception as e:
        print(f"Unexpected error in chat: {e}")
        return jsonify({'error': 'Something went wrong. Please try again.'}), 500
        

    db.session.add(message(session_id=session_id, role='bot', content=reply))
    db.session.commit()
    return jsonify({'response':reply})


@app.route('/history', methods=['GET'])
def history():
    if 'session_id' not in session:
        return jsonify({'messages':[]})
    session_id = session['session_id']
    messages = message.query.filter_by(session_id=session_id).all()

    return jsonify({'messages':[
        {'role':m.role, 'content':m.content}
        for m in messages
    ]})

@app.errorhandler(429)
def rate_limit_exceeded(e):
    return jsonify({'error':'You are sending too many messages at once. Please wait a moment'}), 429


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)