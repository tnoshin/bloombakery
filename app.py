from flask import Flask, request, jsonify, render_template, session
from dotenv import load_dotenv
from openai import OpenAI
from flask_sqlalchemy import SQLAlchemy
import secrets
import os

load_dotenv()

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY')

database_url = os.getenv('DATABASE_URL', 'sqlite:///chat.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://','postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url

db= SQLAlchemy(app)

class message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.String(50))
    role = db.Column(db.String(10))
    content = db.Column(db.Text)

with app.app_context():
    db.create_all()

client = OpenAI(
    api_key=os.getenv('DEEPSEEK_API_KEY'),
    base_url='https://api.deepseek.com'
)
system_prompt = """You are Assistant for Bloom Bakery.
    Menu: Cupcakes $2.99-3.49, Cakes $24.99-28.99, Pastries $2.99-4.99, Drinks $3.99-5.99
    Hours: Mon-Fri 7AM-8PM, Sat-Sun 8AM-9PM
    Location: 142 Rosewood Ave, Brooklyn NY 11201 | Phone: (718) 555-0192
    Stay on-topic. Call user 'Bestie'. Warm tone, use emojis., you are also encouraged to use playful remarks without insulting someone or hurting their feelings.Do not use markdown formatting like asterisks or bold text. Respond in plain text only."""

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    if 'session_id' not in session:
        session['session_id']=secrets.token_hex(8)
    session_id = session['session_id']

    data = request.get_json()
    user_message = data['message']

    db.session.add(message(session_id=session_id, role='user', content=user_message))
    db.session.commit()

    history = message.query.filter_by(session_id=session_id).order_by(message.id.desc()).limit(10).all()
    history = history[::-1] 

    deepseek_messages = [{'role':'system','content': system_prompt}]+[
        {'role':'user' if m.role == 'user' else 'assistant', 'content':m.content}
        for m in history
    ]

    response = client.chat.completions.create(
        model='deepseek-v4-flash',
        messages=deepseek_messages
    )

    reply = response.choices[0].message.content
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



if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)


