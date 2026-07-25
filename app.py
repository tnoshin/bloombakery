from flask import Flask, request, jsonify, render_template, session
from dotenv import load_dotenv
import google.generativeai as genai
from flask_sqlalchemy import SQLAlchemy
import secrets
import os

load_dotenv()

genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-3.1-flash-lite')

app = Flask(__name__)

app.secret_key = os.getenv('SECRET_KEY')
api_key = os.getenv('GEMINI_API_KEY')

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

    user_msg = message(session_id=session_id, role='user', content=user_message)
    db.session.add(user_msg)
    db.session.commit()


    system_prompt = """ You are a helpful assistant for Bloom bakery.

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
    If the message is long, organize it nicely, use bullet points or emojis if necessary. Do not exceed 400 characters when you reply. If asked something unrelated to bakery, politely redirect. DO NOT ENGAGE IN ANY CONVERSATION UNRELATED TO THE BAKERY. Refer to the user as 'Bestie'. 
    Have a friendly personality, use emojis in your texts, you are also encouraged to use playful remarks without insulting someone or hurting their feelings. Do not overuse asterisks or bullet points, start a new line for better readability while lsiting menu ingredients.

    """
    

    

    history = message.query.filter_by(session_id=session_id).order_by(message.id.desc()).limit(10).all()
    history = history[::-1] 

    history_text = ''
    for m in history:
        if m.role == 'user':
            history_text += f'\nUser: {m.content}'
        else:
            history_text += f'\nAssistant: {m.content}'


    full_message = system_prompt + '\n\nConversation so far:' + history_text + '\n\nuser: ' + user_message
    
    response = model.generate_content(full_message)

    bot_msg = message(session_id=session_id, role='bot', content=response.text)
    db.session.add(bot_msg)
    db.session.commit()
    return jsonify({'response':response.text})


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

