from flask import Flask, request, jsonify, redirect, url_for, flash, render_template, Markup, get_flashed_messages, make_response, render_template_string, session, g
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
from app import app, mongo, login_manager
from app.models import User
from pymongo import MongoClient
import datetime
import json
import logging
from werkzeug.utils import secure_filename
import os
from flask_wtf import FlaskForm
from wtforms import StringField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Regexp, Length
from flask_mail import Mail, Message
from flask_caching import Cache

# Configurazione della cache in memoria
app.config['CACHE_TYPE'] = 'SimpleCache' 
app.config['CACHE_DEFAULT_TIMEOUT'] = 300  

cache = Cache(app)  

login_manager = LoginManager() 
login_manager.init_app(app)
login_manager.login_view = 'login'
users_collection = mongo.db.users
products_collection = mongo.db.product

# Configurazione per Flask-Mail con Mailtrap
app.config['MAIL_SERVER'] = 'sandbox.smtp.mailtrap.io'
app.config['MAIL_PORT'] = 2525
app.config['MAIL_USERNAME'] = '43fd97f692e019'
app.config['MAIL_PASSWORD'] = '0d31f2ca91143a'
app.config['MAIL_USE_TLS'] = True  
app.config['MAIL_USE_SSL'] = False  
app.config['MAIL_DEFAULT_SENDER'] = 'noreply@ecommerce.com'  

# Inizializza Flask-Mail
mail = Mail(app)

logging.basicConfig(level=logging.INFO)
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
app.config['SECRET_KEY'] = 'your-secret-key'
app.config['SESSION_TYPE'] = 'filesystem'

@app.route('/guest_alert')
def guest_alert():
    if current_user.is_authenticated:
        return ""
    return render_template_string('''
    <div class="alert alert-dark alert-dismissible fade show text-center mb-0" role="alert" id="guest-alert" style="background-color: #000; color: #fff; border: none;">
        <i class="bi bi-gift-fill me-2" style="color: #fff;"></i>
        <strong>Benvenuto!</strong> Registrati ora e ottieni uno <strong>sconto del 10%</strong> sul tuo primo acquisto.
        <a href="{{ url_for('register', discount='10') }}" class="btn btn-light btn-sm ms-2" style="color: #000;">Crea un account</a>
        <button type="button" class="btn-close small-close" aria-label="Close" data-bs-dismiss="alert"></button>
    </div>
    ''')


@app.before_request
def before_request():
    if 'user_id' in session:
        user_id = session['user_id']
        cart = mongo.db.carts.find_one({'user_id': user_id})
        if cart:
            cart_item_count = sum(item['quantity'] for item in cart['items'])
        else:
            cart_item_count = 0
    else:
        cart_item_count = 0

    g.cart_item_count = cart_item_count
    

class User(UserMixin):
    def __init__(self, user_id):
        self.id = user_id

@login_manager.user_loader 
def load_user(user_id):
    user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    if user:
        return User(user_id=user_id)
    return None

def initialize_session(user):
    session['user_id'] = str(user['_id'])
    session['is_admin'] = user.get('is_admin', False)


@app.context_processor
def inject_user():
    user_id = session.get('user_id')
    if user_id:
        user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if user:
            user['id'] = str(user['_id'])
            return {
                'user': user,
                'logged_in': True,
                'is_admin': user.get('is_admin', False),
                'cart_item_count': g.cart_item_count
            }
    return {'user': None, 'logged_in': False, 'is_admin': False, 'cart_item_count': g.cart_item_count}

@app.route('/logout', methods=['GET'])
def logout():
    
    logout_user()

   
    session.pop('user_id', None)
    session.pop('is_admin', None)

    
    flash('Logged out successfully', 'success')

    
    return redirect(url_for('login'))

@app.route('/')
def index():
    user = current_user if current_user.is_authenticated else None
    cart_item_count = 0
    is_admin = False

    if user:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user.id)})
        cart_item_count = sum(item['quantity'] for item in user_data.get('cart', []))
        is_admin = user_data.get('is_admin', False)
    else:
        cart = get_guest_cart()
        cart_item_count = sum(item['quantity'] for item in cart)

    
    products = list(mongo.db.product.find())

    
    best_sellers = get_best_sellers()
    best_seller_ids = {str(product['_id']) for product in best_sellers}

    
    for product in products:
        product['_id'] = str(product['_id'])
        product['is_best_seller'] = product['_id'] in best_seller_ids

       
        if product.get('discount', 0) > 0:  
            product['original_price'] = product['price']  
            product['price'] = product['price'] - (product['price'] * product['discount'] / 100) 
        else:
            product['original_price'] = product['price']  
    
    return render_template(
        'index.html',
        user=user,
        cart_item_count=cart_item_count,
        is_admin=is_admin,
        products=products,
        best_sellers=best_sellers  
    )

@app.route('/products', methods=['GET'])
def show_products():
    
    category = request.args.get('category')
    color_filter = request.args.get('filter')  
    
    
    query = {}
    
    
    if category:
        query['category'] = category.strip().capitalize()
    
    
    if color_filter:
        query['color'] = color_filter

   
    products = list(mongo.db.product.find(query))

  
    best_sellers = get_best_sellers()
    best_seller_ids = {str(product['_id']) for product in best_sellers}

    
    for product in products:
        product['_id'] = str(product['_id']) 
        product['is_best_seller'] = product['_id'] in best_seller_ids
        
       
        if product.get('discount', 0) > 0:
            product['original_price'] = product['price']
            product['price'] = round(product['price'] - (product['price'] * product['discount'] / 100), 2)

    
    flash_sale_products = [product for product in products if product.get('discount', 0) > 0]

    
    user_id = session.get('user_id', 'guest')
    if user_id == 'guest':
        cart = get_guest_cart()
    else:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        cart = user_data['cart'] if user_data and 'cart' in user_data else []

    cart_item_count = sum(item['quantity'] for item in cart)

   
    return render_template(
        'products.html',
        category=category,              
        products=products,              
        flash_sale_products=flash_sale_products,  
        best_sellers=best_sellers,      
        cart_item_count=cart_item_count 
    )



@app.route('/admin/dashboard')
@login_required
def admin_dashboard():
    if not current_user.is_authenticated or not session.get('is_admin', False):
        return redirect(url_for('index'))  

    return render_template('admin_dashboard.html', user=current_user)


@app.route('/manage_users')
@login_required
def manage_users():
    if not session.get('is_admin', False):
        flash("Accesso non autorizzato!", "danger")
        return redirect(url_for('index'))

    users = mongo.db.users.find()
    return render_template('manager_users.html', users=users)


@app.route('/manage_products', methods=['GET'])
def manage_products():
    products = list(products_collection.find())
    for product in products:
        product['_id'] = str(product['_id'])
    return render_template('manage_products.html', products=products)


@app.route('/products', methods=['GET'])
def get_products():
    products = products_collection.find()
    data = []
    for product in products:
        item = {
            '_id': str(product['_id']),
            'name': product['name'],
            'description': product['description'],
            'price': product['price']
        }
        data.append(item)
    return render_template('manage_products.html', products=data)

@app.route('/api/products', methods=['POST'])
def create_product():
    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price')
    quantity = request.form.get('quantity')
    category = request.form.get('category')
    discount = request.form.get('discount')
    limited_stock = request.form.get('limited_stock')
    availability = request.form.get('availability')
    sizes = request.form.get('sizes').split(',')
    color = request.form.get('color')  # Nuovo campo aggiunto

    if 'images' not in request.files:
        flash('Nessun file di immagine selezionato', 'danger')
        return redirect(url_for('manage_products'))
    
    files = request.files.getlist('images')

    image_urls = []
    for file in files:
        if file.filename == '':
            continue

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_urls.append(f'/static/uploads/{filename}')
        else:
            flash('Formato file non valido', 'danger')
            return redirect(url_for('manage_products'))

    if not name or not description or not price or not quantity:
        flash('Dati mancanti o non validi', 'danger')
        return redirect(url_for('manage_products'))

    try:
        price = float(price)
        quantity = int(quantity)
        discount = int(discount) if discount else 0
        limited_stock = int(limited_stock) if limited_stock else 0
        if price <= 0 or quantity < 0 or discount < 0 or discount > 100 or limited_stock < 0:
            flash('Dati non validi. Controlla i valori inseriti.', 'danger')
            return redirect(url_for('manage_products'))
    except ValueError:
        flash('Formato prezzo o quantità non valido', 'danger')
        return redirect(url_for('manage_products'))

    if not image_urls:
        image_urls.append('https://dummyimage.com/450x300/dee2e6/6c757d.jpg')

    original_price = price
    if discount > 0:
        price = price - (price * discount / 100)

    product = {
        'name': name,
        'description': description,
        'price': price,
        'original_price': original_price,
        'quantity': quantity,
        'image_urls': image_urls,
        'category': category,
        'discount': discount,
        'limited_stock': limited_stock,
        'availability': availability,
        'sizes': sizes,
        'color': color,  
        'views': 0,
        'purchases': 0,
        'reviews': []
    }

    try:
        product_id = products_collection.insert_one(product).inserted_id
        flash('Prodotto creato con successo!', 'success')
    except Exception as e:
        flash(f'Errore durante l\'inserimento del prodotto: {str(e)}', 'danger')

    return redirect(url_for('manage_products'))


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/products/<id>', methods=['GET'])
def get_product(id):
    try:
        product = products_collection.find_one({'_id': ObjectId(id)})
        if product:
            item = {
                '_id': str(product['_id']),
                'name': product['name'],
                'description': product['description'],
                'price': product['price']
            }
            return jsonify(item), 200
        return jsonify({'msg': 'Product not found'}), 404
    except Exception as e:
        return jsonify({'msg': str(e)}), 500

@app.route('/update_product/<product_id>', methods=['POST'])
def update_product(product_id):
    try:
        updated_name = request.form.get('name')
        updated_description = request.form.get('description')
        updated_price = request.form.get('price')

        files = request.files.getlist('images')
        image_urls = []

        for file in files:
            if file.filename == '':
                continue

            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                image_urls.append(f'/static/uploads/{filename}')
            else:
                flash('Formato file non valido', 'danger')
                return redirect(url_for('manage_products'))

        update_data = {
            'name': updated_name,
            'description': updated_description,
            'price': updated_price
        }

        if image_urls:
            update_data['image_urls'] = image_urls

        products_collection.update_one(
            {'_id': ObjectId(product_id)},
            {'$set': update_data}
        )
        flash('Prodotto aggiornato con successo', 'success')
        return redirect(url_for('manage_products'))
    except Exception as e:
        flash(f'Errore durante l\'aggiornamento del prodotto: {str(e)}', 'danger')
        return redirect(url_for('manage_products'))


@app.route('/api/products/<product_id>', methods=['DELETE'])
def delete_cart_item(product_id):
    try:
        user_id = session.get('user_id', 'guest')
        if user_id == 'guest':
            cart = get_guest_cart()
            cart = [product for product in cart if product['product_id'] != product_id]
            save_guest_cart(cart)
        else:
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user or 'cart' not in user:
                return jsonify({'message': 'Cart not found'}), 404
            user['cart'] = [product for product in user['cart'] if product['product_id'] != product_id]
            mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'cart': user['cart']}})
            cart = user['cart']

        cart_item_count = sum(product['quantity'] for product in cart)
        response = {
            'message': 'Product removed successfully!',
            'cart_item_count': cart_item_count
        }

       
        if 'HX-Request' in request.headers:
            
            return render_template_string(
                '''
                <div class="alert alert-success" role="alert">
                    {{ message }}
                </div>
                ''',
                message=response['message']
            )

        
        return jsonify(response), 200
    except Exception as e:
        return jsonify({'message': str(e)}), 500
@app.route('/users', methods=['GET'])
def get_users():
    users = mongo.db.users.find()
    data = []
    for user in users:
        item = {
            '_id': str(user['_id']),
            'username': user['username'],
            'email': user['email'],
            'is_admin': user.get('is_admin', False),  
            'created_at': user.get('created_at', datetime.datetime.utcnow())
        }
        data.append(item)
    return jsonify(data), 200


@app.route('/login', methods=['GET', 'POST'])
def login():
    next_page = request.args.get('next', 'index')  

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = mongo.db.users.find_one({'username': username})

        if not user:
            flash('Username does not exist', 'danger')
            if 'HX-Request' in request.headers:
                return render_template('_login_form.html', next=next_page), 200  
            else:
                return render_template('login.html', next=next_page)

        if not check_password_hash(user['password'], password):
            flash('Invalid password', 'danger')
            if 'HX-Request' in request.headers:
                return render_template('_login_form.html', next=next_page), 200
            else:
                return render_template('login.html', next=next_page)

        # Inizializzazione della sessione utente
        session['user_id'] = str(user['_id'])
        session['is_admin'] = user.get('is_admin', False)
        user_obj = User(user_id=str(user['_id']))
        login_user(user_obj)

        flash('Login successful!', 'success')

        
        redirect_url = url_for('checkout') if next_page == 'checkout' else url_for(next_page)
        if 'HX-Request' in request.headers:
            return '', 204, {'HX-Redirect': redirect_url}
        else:
            return redirect(redirect_url)

    cart_item_count = get_cart_item_count(session.get('user_id')) if session.get('user_id') else 0
    return render_template('login.html', next=next_page, cart_item_count=cart_item_count)


@app.route('/register', methods=['GET', 'POST'])
def register():
    next_page = request.args.get('next', 'index')  
    discount_eligible = request.args.get('discount', 'false') == '10'

    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        first_name = request.form.get('first_name')
        last_name = request.form.get('last_name')
        address = request.form.get('address')
        city = request.form.get('city')
        cap = request.form.get('cap')
        country = request.form.get('country')

        
        if not username or not email or not password or not first_name or not last_name or not address or not city or not cap or not country:
            flash('Missing required fields', 'danger')
            return render_template('register.html', next=next_page, cart_item_count=get_cart_item_count(session.get('user_id')))

        
        existing_user = mongo.db.users.find_one({'username': username})
        if existing_user:
            flash('Username already exists', 'danger')
            return render_template('register.html', next=next_page, cart_item_count=get_cart_item_count(session.get('user_id')))

        
        hashed_password = generate_password_hash(password)

       
        user_data = {
            'username': username,
            'email': email,
            'password': hashed_password,
            'first_name': first_name,
            'last_name': last_name,
            'address': address,
            'city': city,
            'cap': cap,
            'country': country,
            'created_at': datetime.datetime.utcnow(),
            'discount_eligible': discount_eligible  
        }

        try:
            
            user_id = mongo.db.users.insert_one(user_data).inserted_id
            user = mongo.db.users.find_one({'_id': user_id})  

            
            guest_cart = get_guest_cart()
            if guest_cart:
                mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'cart': guest_cart}})
                save_guest_cart([])  

            
            initialize_session(user)

            
            flash('Registration successful! Use code WELCOME10 to get 10% off your first order.', 'success')

            
            if 'HX-Request' in request.headers:
                return '', 204, {'HX-Redirect': url_for('login', next=next_page)}
            else:
                return redirect(url_for('login', next=next_page))

        except Exception as e:
            flash('An error occurred: {}'.format(str(e)), 'danger')
            return render_template('register.html', next=next_page, cart_item_count=get_cart_item_count(session.get('user_id')))

    return render_template('register.html', next=next_page, cart_item_count=get_cart_item_count(session.get('user_id')))



@app.route('/profile')
@login_required
def profile():
   
    user_data = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})
    
    if user_data:
        user = {
            'first_name': user_data.get('first_name'),
            'last_name': user_data.get('last_name'),
            'email': user_data.get('email')
        }
        cart_item_count = sum(item['quantity'] for item in user_data.get('cart', []))
        is_admin = user_data.get('is_admin', False)
    else:
       
        user = None
        cart_item_count = 0
        is_admin = False

    return render_template(
        'profile.html',
        user=user,
        cart_item_count=cart_item_count,
        is_admin=is_admin
    )

@app.route('/settings')
@login_required
def settings():
    return render_template('settings.html', user=current_user)

# Import necessari, se non già importati
from flask import jsonify, render_template


# Route per caricare gli indirizzi
@app.route('/addresses', methods=['GET'])
@login_required
def addresses():
    user = current_user
    
    addresses = user.addresses if hasattr(user, 'addresses') else []
    return render_template('partials/addresses.html', addresses=addresses)

# Route per caricare i metodi di pagamento
@app.route('/payment_methods', methods=['GET'])
@login_required
def payment_methods():
    user = current_user
    
    payment_methods = user.payment_methods if hasattr(user, 'payment_methods') else []
    return render_template('partials/payment_methods.html', payment_methods=payment_methods)

@app.route('/preferences', methods=['GET'])
@login_required
def preferences():
    user = current_user
   
    preferences = user.preferences if hasattr(user, 'preferences') else {}
    return render_template('partials/preferences.html', preferences=preferences)


@app.route('/security', methods=['GET'])
@login_required
def security():
    user = current_user
    
    security_settings = user.security_settings if hasattr(user, 'security_settings') else {}
    return render_template('partials/security.html', security_settings=security_settings)


@app.route('/api/cart/<user_id>', methods=['POST'])
def add_to_cart(user_id):
    data = request.get_json() if request.is_json else request.form
    product_id = data.get('product_id')
    size = data.get('size')
    quantity = int(data.get('quantity', 1))

    logging.info(f"Adding to cart: product_id={product_id}, size={size}, quantity={quantity}, user_id={user_id}")

    product = products_collection.find_one({'_id': ObjectId(product_id)})

    if not product:
        logging.error("Product not found")
        return jsonify({'error': 'Product not found'}), 404

    
    price = product['price']
    if 'discount' in product and product['discount'] > 0:
        
        original_price = price
        price = original_price - (original_price * product['discount'] / 100)
    else:
        original_price = price  

    
    if 'image_urls' in product and product['image_urls']:
        image_url = product['image_urls'][0]
    else:
        image_url = product.get('image_url', 'https://dummyimage.com/450x300/dee2e6/6c757d.jpg')
    
    if not image_url.startswith('/static/'):
        image_url = f'/static/uploads/{image_url}'

    cart_item = {
        'product_id': product_id,
        'quantity': quantity,
        'size': size,
        'name': product['name'],
        'price': price,  
        'original_price': original_price,  
        'image_url': image_url
    }

    if user_id == 'guest':
        cart = get_guest_cart()
        logging.info(f"Guest cart before update: {cart}")
        for item in cart:
            if item['product_id'] == product_id and item.get('size') == size:
                item['quantity'] += quantity
                break
        else:
            cart.append(cart_item)
        save_guest_cart(cart)
        cart_item_count = sum(item['quantity'] for item in cart)
        logging.info(f"Guest cart after update: {cart}")
    else:
        user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if user:
            if 'cart' not in user:
                user['cart'] = []
            for item in user['cart']:
                if item['product_id'] == product_id and item.get('size') == size:
                    item['quantity'] += quantity
                    break
            else:
                user['cart'].append(cart_item)
            mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'cart': user['cart']}})
            cart_item_count = sum(item['quantity'] for item in user['cart'])
        else:
            logging.error("User not found")
            return jsonify({'error': 'User not found'}), 404

    
    products_collection.update_one({"_id": ObjectId(product_id)}, {"$inc": {"purchases": quantity}})

    response_html = render_template_string(
        '''
        <div class="cart-preview show p-3 border shadow-sm" id="cart-preview">
            <div class="d-flex justify-content-between align-items-center">
                <h6 class="mb-0">Prodotto aggiunto al carrello!</h6>
                <button type="button" class="btn-close" aria-label="Close" hx-get="{{ url_for('close_cart_preview') }}" hx-target="#cart-preview-container" hx-swap="outerHTML"></button>
            </div>
            <hr>
            <div class="d-flex">
               <img src="{{ image_url }}" alt="{{ product_name }}" class="img-fluid me-3" style="width: 100px; height: 100px; object-fit: cover; border-radius: 4px;">
                <div>
                    <p class="mb-1"><strong>{{ product_name }}</strong></p>
                    <p class="mb-1">Quantità: {{ quantity }}</p>
                    <p class="mb-1">Prezzo: <span class="text-success">€{{ price }}</span></p>
                    <p class="mb-1">Taglia: {{ size }}</p>
                </div>
            </div>
            <hr>
            <div class="d-flex justify-content-end">
                <a href="{{ url_for('view_cart', user_id=user_id) }}" class="btn btn-outline-dark btn-sm flex-grow-1 rounded-0">Vai al carrello</a>
                <button type="button" class="btn btn-outline-dark btn-sm flex-grow-1 rounded-0" hx-get="{{ url_for('close_cart_preview') }}" hx-target="#cart-preview-container" hx-swap="outerHTML">Continua a fare shopping</button>
            </div>
        </div>
        <span class="badge bg-dark text-white ms-1 rounded-pill" id="cart-badge" hx-swap-oob="true">{{ cart_item_count }}</span>
        ''',
        product_name=product['name'],
        quantity=quantity,
        price=price, 
        size=size,
        user_id=user_id,
        image_url=image_url,
        cart_item_count=cart_item_count
    )

    response = make_response(response_html)

    
    response.headers['HX-Trigger'] = json.dumps({
        'updateCartBadge': cart_item_count,  
        'updateShipping': True  
    })

    return response



@app.route('/api/select_size', methods=['POST'])
def select_size():
    data = request.get_json() if request.is_json else request.form
    product_id = data.get('product_id')
    size = data.get('size')

    if not product_id or not size:
        return jsonify({'error': 'Invalid data'}), 400

    response_html = render_template_string(
        '''
        <button class="btn btn-outline-dark uniform-button"
                type="button"
                id="add-to-cart-{{ product_id }}"
                hx-post="{{ url_for('add_to_cart', user_id=user.id if user else 'guest') }}"
                hx-trigger="click"
                hx-vals='{"product_id": "{{ product_id }}", "quantity": 1, "size": "{{ size }}"}'
                hx-target="#cart-preview-container"
                hx-swap="innerHTML"
                hx-trigger="event:add-to-cart"
                hx-on="htmx:afterRequest update-shipping">
            Aggiungi al carrello
        </button>
        <div id="size-indicator-{{ product_id }}"></div>
        ''',
        product_id=product_id, size=size
    )

    return response_html




@app.route('/close-cart-preview', methods=['GET'])
def close_cart_preview():
    return '<div></div>', 200  

@app.route('/cart/items/<product_id>', methods=['PUT'])
def update_cart_item(product_id):
    data = request.form
    app.logger.debug(f"Richiesta PUT ricevuta per product_id: {product_id}")
    
    try:
        quantity = int(data['quantity'])
        if quantity < 1:
            return jsonify({'error': 'Quantity must be at least 1'}), 400

        user_id = session.get('user_id')
        cart = []
        if user_id:
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user or 'cart' not in user:
                return jsonify({'msg': 'Cart not found'}), 404

            for product in user['cart']:
                if product['product_id'] == product_id:
                    product['quantity'] = quantity
                    full_product = products_collection.find_one({'_id': ObjectId(product_id)})
                    if full_product:
                        product['name'] = full_product['name']
                        product['price'] = full_product['price']
                        if 'image_urls' in full_product and full_product['image_urls']:
                            product['image_url'] = full_product['image_urls'][0]
                        else:
                            product['image_url'] = full_product.get('image_url', 'https://dummyimage.com/450x300/dee2e6/6c757d.jpg')
                    break
            mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'cart': user['cart']}})
            cart = user['cart']
        else:
            cart = get_guest_cart()
            for product in cart:
                if product['product_id'] == product_id:
                    product['quantity'] = quantity
                    full_product = products_collection.find_one({'_id': ObjectId(product_id)})
                    if full_product:
                        product['name'] = full_product['name']
                        product['price'] = full_product['price']
                        if 'image_urls' in full_product and full_product['image_urls']:
                            product['image_url'] = full_product['image_urls'][0]
                        else:
                            product['image_url'] = full_product.get('image_url', 'https://dummyimage.com/450x300/dee2e6/6c757d.jpg')
                    break
            save_guest_cart(cart)

        
        subtotal = sum(product['price'] * product['quantity'] for product in cart)
        cart_item_count = sum(product['quantity'] for product in cart)

       
        app.logger.debug(f"Cart item count dopo l'aggiornamento: {cart_item_count}, Subtotal: {subtotal}")

        
        updated_product_html = render_template('cart_item.html', product=product, cart_item_count=cart_item_count, subtotal=subtotal)

        
        response = make_response(updated_product_html)

        
        response.headers['HX-Trigger'] = json.dumps({
            'updateCartBadge': cart_item_count,
            'updateSubtotal': f"€{subtotal:.2f}"
        })

        
        response.set_cookie('cart_item_count', str(cart_item_count), max_age=30*24*60*60)

        return response
    except Exception as e:
        app.logger.error(f"Errore durante l'aggiornamento dell'articolo nel carrello: {e}")
        return jsonify({'error': 'Internal server error'}), 500




@app.route('/cart/items/<product_id>', methods=['DELETE'])
def remove_from_cart(product_id):
    try:
        
        size = request.args.get('size')

        if not size:
            return jsonify({'error': 'Size parameter is required'}), 400

        user_id = session.get('user_id')
        if user_id:
            user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
            if not user or 'cart' not in user:
                return jsonify({'msg': 'Cart not found'}), 404

            
            original_cart_length = len(user['cart'])
            user['cart'] = [product for product in user['cart'] if not (product['product_id'] == product_id and product['size'] == size)]

            if len(user['cart']) == original_cart_length:
                return jsonify({'msg': 'Product not found in cart'}), 404

            mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'cart': user['cart']}})
            cart = user['cart']
        else:
            cart = get_guest_cart()
            original_cart_length = len(cart)
            
            cart = [product for product in cart if not (product['product_id'] == product_id and product['size'] == size)]

            if len(cart) == original_cart_length:
                return jsonify({'msg': 'Product not found in cart'}), 404

            save_guest_cart(cart)

        cart_item_count = sum(product['quantity'] for product in cart)
        response = make_response(render_template_string('<div class="alert alert-success">Il prodotto è stato eliminato correttamente!</div>'))
        response.set_cookie('cart_item_count', str(cart_item_count), max_age=30*24*60*60)
        return response
    except Exception as e:
        print(f"Error removing from cart: {str(e)}")
        return jsonify({'error': str(e)}), 500


def get_guest_cart():
    cart = session.get('guest_cart', [])
    logging.info(f"Retrieved guest cart: {cart}")
    return cart

def save_guest_cart(cart):
    session['guest_cart'] = cart
    response = make_response(jsonify({'success': True}), 200)
    logging.info(f"Saved guest cart: {cart}")
    return response

@app.route('/api/cart/<string:user_id>', methods=['GET'])
def view_cart(user_id):
    items = []
    colors_in_cart = set()
    has_tshirt = False  
    has_sweatshirt = False  
    set_discount = 0.15 

    if user_id == 'guest':
        cart = get_guest_cart()
    else:
        user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        cart = user['cart'] if user and 'cart' in user else []

    for product in cart:
        item = mongo.db.product.find_one({'_id': ObjectId(product['product_id'])})
        if item:
            image_url = item['image_urls'][0] if 'image_urls' in item and item['image_urls'] else item.get('image_url', 'https://dummyimage.com/450x300/dee2e6/6c757d.jpg')
            price = item['price'] - item.get('discount', 0)

           
            if item['category'].lower() in ['magliette', 'cappelli']:
                has_tshirt = True
            if item['category'].lower() == 'felpe':
                has_sweatshirt = True

            items.append({
                'product_id': str(item['_id']),
                'name': item['name'],
                'image_url': image_url,
                'quantity': product['quantity'],
                'price': price,
                'size': product.get('size')
            })
            
            if 'color' in item:
                colors_in_cart.add(item['color'])

    cart_item_count = sum(item['quantity'] for item in items)
    subtotal = sum(item['price'] * item['quantity'] for item in items)

   
    if has_tshirt and has_sweatshirt:
        discount_amount = subtotal * set_discount
    else:
        discount_amount = 0

    subtotal_after_discount = subtotal - discount_amount

   
    recommended_products = []
    if colors_in_cart:
        
        recommended_products = list(mongo.db.product.find({'color': {'$in': list(colors_in_cart)}}).limit(4))

    if request.headers.get('Accept') == 'application/json':
        return jsonify({
            'cart': items, 
            'cart_item_count': cart_item_count, 
            'subtotal': subtotal_after_discount,
            'discount_amount': discount_amount,
            'recommended_products': recommended_products,
            'has_tshirt': has_tshirt,
            'has_sweatshirt': has_sweatshirt
        })
    else:
        response = make_response(render_template(
            'cart.html', 
            cart=items, 
            cart_item_count=cart_item_count, 
            subtotal=subtotal_after_discount, 
            discount_amount=discount_amount,
            has_tshirt=has_tshirt,  
            has_sweatshirt=has_sweatshirt,  
            recommended_products=recommended_products
        ))
        response.set_cookie('cart_item_count', str(cart_item_count), max_age=30*24*60*60)
        return response


    
def get_cart_item_count(user_id):
    if user_id:
        user = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if user and 'cart' in user:
            return sum(item['quantity'] for item in user['cart'])
    else:
        cart = get_guest_cart()
        return sum(item['quantity'] for item in cart)
    return 0

@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    user_id = session.get('user_id', 'guest')
    user_data = None
    show_guest_modal = False
    discount_code_applied = False
    discount_code_error = None
    discount_amount = 0
    has_tshirt = False
    has_sweatshirt = False
    has_cap = False
    has_tote_bag = False
    set_discount = 0.15
    registration_discount = 0.1

    if user_id == 'guest':
        cart = get_guest_cart()
        show_guest_modal = True
    else:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        cart = user_data['cart'] if user_data and 'cart' in user_data else []

    if request.method == 'POST':
        discount_code = request.form.get('discount_code', '').strip()

        
        if discount_code == 'WELCOME10':
            if user_data and user_data.get('discount_eligible', True):
                discount_code_applied = True
            else:
                discount_code_error = "Codice sconto non valido o non applicabile."

    if not cart:
        flash('Il tuo carrello è vuoto. Aggiungi prodotti prima di procedere al checkout.', 'danger')
        return redirect(url_for('view_cart', user_id=user_id))

   
    for product in cart:
        item = mongo.db.product.find_one({'_id': ObjectId(product['product_id'])})
        if item:
            if 'image_urls' in item and item['image_urls']:
                product['image_url'] = item['image_urls'][0]
            else:
                product['image_url'] = item.get('image_url', 'https://dummyimage.com/450x300/dee2e6/6c757d.jpg')
            
            if not product['image_url'].startswith('/static/'):
                product['image_url'] = f'/static/uploads/{product["image_url"]}'

            
            if item['category'].lower() == 'magliette':
                has_tshirt = True
            if item['category'].lower() == 'felpe':
                has_sweatshirt = True
            if item['category'].lower() == 'cappelli':
                has_cap = True
            if item['category'].lower() == 'sacche di tela':
                has_tote_bag = True

            if 'discount' in item and item['discount'] > 0:
                product['original_price'] = item['price']
                product['price'] = item['price'] - item['discount']
            else:
                product['price'] = item['price']

    subtotal = sum(item['price'] * item['quantity'] for item in cart)

    
    if (has_tshirt and has_sweatshirt) or (has_cap and has_tote_bag):
        set_discount_amount = round(subtotal * set_discount, 2)
    else:
        set_discount_amount = 0

    
    if discount_code_applied:
        discount_amount = round(subtotal * registration_discount, 2)

    
    total_discount_amount = max(set_discount_amount, discount_amount)

    total = round(subtotal - total_discount_amount, 2)
    shipping_cost = 0 if total >= 40 else 5
    total = round(total + shipping_cost, 2)
    cart_item_count = sum(item['quantity'] for item in cart)

    
    if request.method == 'POST' and request.headers.get('HX-Request'):
        return render_template(
            'checkout_summary.html',
            cart=cart,
            subtotal=round(subtotal, 2),
            discount_amount=round(total_discount_amount, 2),
            total=round(total, 2),
            shipping_cost=round(shipping_cost, 2),
            discount_code_applied=discount_code_applied,
            discount_code_error=discount_code_error
        )

    return render_template(
        'checkout.html',
        cart=cart,
        subtotal=round(subtotal, 2),
        discount_amount=round(total_discount_amount, 2),
        total=round(total, 2),
        shipping_cost=round(shipping_cost, 2),
        cart_item_count=cart_item_count,
        user_data=user_data,
        show_guest_modal=show_guest_modal,
        discount_code_applied=discount_code_applied,
        discount_code_error=discount_code_error
    )





@app.route('/create_order', methods=['POST'])
def create_order():
    user_id = session.get('user_id', 'guest')
    cart = get_guest_cart() if user_id == 'guest' else mongo.db.users.find_one({'_id': ObjectId(user_id)})['cart']
    email = request.form.get('email') if user_id == 'guest' else mongo.db.users.find_one({'_id': ObjectId(user_id)})['email']

   
    session.pop('_flashes', None)

    if not cart:
        flash('Il tuo carrello è vuoto. Aggiungi prodotti prima di procedere al checkout.', 'danger')
        return redirect(url_for('view_cart', user_id=user_id))

    subtotal = sum(item['price'] * item['quantity'] for item in cart)
    shipping_cost = 0 if subtotal >= 40 else 5  
    total_order = subtotal + shipping_cost

    discount_amount = 0
    for item in cart:
        if item.get('discount'):
            discount_amount += item['discount'] * item['quantity']

    total_order -= discount_amount

    shipping_details = {
        'name': request.form['name'],
        'address': request.form['address'],
        'city': request.form['city'],
        'cap': request.form['cap'],
        'country': request.form['country']
    }
    payment_details = {
        'card_number': request.form['card_number'],
        'expiry_date': request.form['expiry_date'],
        'cvv': request.form['cvv']
    }

    order_id = mongo.db.orders.insert_one({
        'user_id': user_id if user_id != 'guest' else None,
        'cart': cart,
        'email': email,
        'shipping_details': shipping_details,
        'payment_details': payment_details,
        'status': 'completed',
        'created_at': datetime.datetime.utcnow(),
        'total': total_order
    }).inserted_id

    try:
        for item in cart:
            product_id = item['product_id']
            quantity = item['quantity']
            products_collection.update_one({"_id": ObjectId(product_id)}, {"$inc": {"purchases": quantity}})
        
        if user_id == 'guest':
            save_guest_cart([])  
        else:
            mongo.db.users.update_one({'_id': ObjectId(user_id)}, {'$set': {'cart': []}}) 

        send_order_confirmation_email(email, order_id, cart, shipping_details)
        
        flash('Ordine effettuato con successo! Riceverai una conferma via email.', 'success')

        
        return redirect(url_for('order_confirmation', order_id=str(order_id)))
        
    except Exception as e:
        app.logger.error(f"Errore durante l'invio della conferma dell'ordine: {str(e)}")
        flash('Errore durante l\'invio della conferma dell\'ordine. Controlla il tuo indirizzo email e riprova.', 'danger')
        mongo.db.orders.delete_one({'_id': order_id})
        
        return render_template('checkout.html', cart=cart, subtotal=subtotal, total=total_order, shipping_cost=shipping_cost, discount_amount=discount_amount, show_guest_modal=(user_id == 'guest'))

def send_order_confirmation_email(email, order_id, cart, shipping_details):
    try:
        mail = Mail(app)
        msg = Message("Conferma del tuo ordine", sender="noreply@ecommerce.com", recipients=[email])
        msg.body = render_template('email_order_confirmation.txt', order_id=order_id, cart=cart, shipping_details=shipping_details)
        mail.send(msg)
    except Exception as e:
        app.logger.error(f"Errore nell'invio dell'email: {str(e)}")
        flash('Errore durante l\'invio della conferma dell\'ordine. Controlla il tuo indirizzo email e riprova.', 'danger')

@app.route('/order_confirmation/<order_id>', methods=['GET'])
def order_confirmation(order_id):
    
    order = mongo.db.orders.find_one({'_id': ObjectId(order_id)})

    if not order:
        flash('Ordine non trovato.', 'danger')
        return redirect(url_for('index'))

   
    for item in order['cart']:
        product = products_collection.find_one({'_id': ObjectId(item['product_id'])})
        if product:
            
            if 'image_urls' in product and product['image_urls']:
                item['image_url'] = product['image_urls'][0]  
            else:
                item['image_url'] = product.get('image_url', 'https://dummyimage.com/450x300/dee2e6/6c757d.jpg')

    
    return render_template('order_confirmation.html', order=order)


@app.route('/search', methods=['GET'])
def search():
    query = request.args.get('query', '')
    category = request.args.get('category', '')
    min_price = request.args.get('min_price', 0)
    max_price = request.args.get('max_price', 0)
    color = request.args.get('color', '')
    size = request.args.get('size', '')

    search_filter = {}

    if query:
        search_filter['name'] = {'$regex': query, '$options': 'i'}
    if category:
        search_filter['category'] = category
    if min_price:
        search_filter['price'] = {'$gte': float(min_price)}
    if max_price:
        if 'price' in search_filter:
            search_filter['price']['$lte'] = float(max_price)
        else:
            search_filter['price'] = {'$lte': float(max_price)}
    if color:
        search_filter['color'] = color
    if size:
        search_filter['sizes'] = size

    results = products_collection.find(search_filter)
    products_list = list(results)
    
    flash_sale_products = []

    for product in products_list:
        product['_id'] = str(product['_id'])
        if product.get('discount', 0) > 0:
            product['original_price'] = product['price']
            product['price'] = product['price'] - product['discount']
            flash_sale_products.append(product)

   
    all_products = list(products_collection.find())  
    for product in all_products:
        if product.get('discount', 0) > 0:
            product['original_price'] = product['price']
            product['price'] = product['price'] - product['discount']
            flash_sale_products.append(product)

    user_id = session.get('user_id')
    cart_item_count = get_cart_item_count(user_id)

    return render_template('search_results.html', products=products_list, flash_sale_products=flash_sale_products, query=query, cart_item_count=cart_item_count)

@app.route('/product/<id>', methods=['GET'])
def product_detail(id):
    try:
        product = products_collection.find_one({"_id": ObjectId(id)})
        if not product:
            return jsonify({'message': 'Product not found'}), 404

        # Incrementa il contatore delle visualizzazioni
        products_collection.update_one({"_id": ObjectId(id)}, {"$inc": {"views": 1}})
        product['views'] = product.get('views', 0) + 1  # Aggiorna il valore delle visualizzazioni per il rendering

        product['_id'] = str(product['_id'])
        product['quantity'] = product.get('quantity', 0)  
        product['purchases'] = product.get('purchases', 0)  

        # Calcola il prezzo originale e quello scontato
        if product.get('discount', 0) > 0:
            product['original_price'] = product['price']  # Salva il prezzo originale
            product['price'] = product['price'] - (product['price'] * product['discount'] / 100)  
        else:
            product['original_price'] = product['price']  # Assicura che 'original_price' venga impostato anche senza sconto

        # Verifica se il prodotto è un best seller nella sua categoria
        category = product.get('category')
        best_sellers = get_best_sellers(category=category, limit=3)
        best_seller_ids = {str(p['_id']) for p in best_sellers}
        product['is_best_seller'] = str(product['_id']) in best_seller_ids

        # Recupera tutte le recensioni del prodotto
        product_reviews = list(mongo.db.reviews.find({'product_id': ObjectId(id)}))

        user_id = session.get('user_id')
        cart_item_count = get_cart_item_count(user_id)

        if 'application/json' in request.headers.get('Accept'):
            return jsonify(product=product, reviews=product_reviews), 200
        else:
            return render_template('product_detail.html', product=product, reviews=product_reviews, cart_item_count=cart_item_count)

    except Exception as e:
        return jsonify({'error': str(e)}), 500




@app.route('/products/<product_id>/reviews', methods=['POST'])
@login_required
def add_review(product_id):
    
    app.logger.info(f"Received form data: {request.form}")
    
    review_text = request.form.get('reviewText')
    app.logger.info(f"Received reviewText: {review_text}")

    if not review_text:
        app.logger.error("Review text is required but not provided.")
        return '<div hx-swap-oob="true" class="alert alert-danger" role="alert">Il testo della recensione è obbligatorio.</div>', 400

    # Carica l'immagine se presente
    photo_url = None
    if 'reviewPhoto' in request.files:
        file = request.files['reviewPhoto']
        app.logger.info(f"Review photo file: {file.filename}")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(app.static_folder, 'uploads', 'reviews')
            
            # Verifica se la directory esiste, altrimenti creala
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            
            file_path = os.path.join(upload_folder, filename)
            try:
                file.save(file_path)
                photo_url = url_for('static', filename=f'uploads/reviews/{filename}')
            except Exception as e:
                app.logger.error(f"Errore nel salvataggio del file: {e}")
                return '<div hx-swap-oob="true" class="alert alert-danger" role="alert">Errore nel caricamento dell\'immagine.</div>', 500
        else:
            app.logger.error("File non valido o non consentito.")
            return '<div hx-swap-oob="true" class="alert alert-danger" role="alert">Formato del file non consentito.</div>', 400

    # Trova l'utente attuale
    user = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})
    if not user:
        app.logger.error("User not found.")
        return '<div hx-swap-oob="true" class="alert alert-danger" role="alert">Utente non trovato.</div>', 404

    # Crea la recensione con tutti i dettagli
    review = {
        '_id': ObjectId(),  # Crea un ID univoco per la recensione
        'product_id': ObjectId(product_id),
        'username': user['username'],
        'text': review_text,
        'date': datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S'),
        'photo': photo_url  # Aggiungi l'URL della foto
    }

    # Inserisce la recensione nella collezione `reviews`
    mongo.db.reviews.insert_one(review)

    # Recupera il prodotto attuale per ottenere ulteriori dettagli
    product = mongo.db.product.find_one({'_id': ObjectId(product_id)})

    
    if 'image_urls' in product and product['image_urls']:
        image_url = product['image_urls'][0]  # Prendi la prima immagine dalla lista
    else:
        image_url = product.get('image_url', 'https://dummyimage.com/450x300/dee2e6/6c757d.jpg')

    # Recupera tutte le recensioni del prodotto
    product_reviews = list(mongo.db.reviews.find({'product_id': ObjectId(product_id)}))

    
    return render_template('reviews.html', reviews=product_reviews, product=product, image_url=image_url), 200

@app.route('/products/<product_id>/upload_photo', methods=['POST'])
@login_required
def upload_photo(product_id):
    # Carica l'immagine se presente
    photo_url = None
    if 'reviewPhoto' in request.files:
        file = request.files['reviewPhoto']
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            upload_folder = os.path.join(app.static_folder, 'uploads', 'reviews')
            
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
            
            file_path = os.path.join(upload_folder, filename)
            try:
                file.save(file_path)
                photo_url = url_for('static', filename=f'uploads/reviews/{filename}')
                return '<div class="alert alert-success" role="alert">Foto caricata con successo!</div>', 200
            except Exception as e:
                app.logger.error(f"Errore nel salvataggio del file: {e}")
                return '<div class="alert alert-danger" role="alert">Errore nel caricamento dell\'immagine.</div>', 500
        else:
            return '<div class="alert alert-danger" role="alert">Formato del file non consentito.</div>', 400

    return '<div class="alert alert-danger" role="alert">Nessuna foto caricata.</div>', 400

@app.route('/api/products/<product_id>', methods=['DELETE'])
def delete_product(product_id):
    try:
        # Verifica se l'ID del prodotto è valido e se il prodotto esiste nel database
        product = products_collection.find_one({'_id': ObjectId(product_id)})
        if not product:
            flash('Prodotto non trovato!', 'danger')
            return jsonify({'message': 'Product not found'}), 404
        
       
        result = products_collection.delete_one({'_id': ObjectId(product_id)})
        if result.deleted_count == 1:
            flash('Prodotto eliminato con successo!', 'success')
            app.logger.info(f"Prodotto con ID {product_id} eliminato correttamente.")
        else:
            flash('Errore durante l\'eliminazione del prodotto!', 'danger')
            app.logger.error(f"Errore: il prodotto con ID {product_id} non è stato eliminato.")
            return jsonify({'message': 'Deletion failed'}), 500
    
    except Exception as e:
        app.logger.error(f"Errore durante l'eliminazione del prodotto con ID {product_id}: {str(e)}")
        flash(f'Errore durante l\'eliminazione del prodotto: {str(e)}', 'danger')
        return jsonify({'message': str(e)}), 500

    
    if 'HX-Request' in request.headers:
        return render_template_string(
            '''
            {% with messages = get_flashed_messages(with_categories=true) %}
                {% if messages %}
                    {% for category, message in messages %}
                        <div class="alert alert-{{ category }} mt-3" role="alert">
                            {{ message }}
                        </div>
                    {% endfor %}
                {% endif %}
            {% endwith %}
            '''
        )
    else:
        return redirect(url_for('manage_products'))


@app.route('/show_free_shipping_message', methods=['GET'])
def show_free_shipping_message():
    response_html = render_template_string(
        '''
        <div class="fade-in">
            <div class="alert alert-success" role="alert">
                Spedizione gratuita per ordini superiori a 40€!
            </div>
        </div>
        '''
    )
    return response_html

@app.route('/show_special_offer', methods=['GET'])
def show_special_offer():
    response_html = render_template_string(
        '''
        <div class="alert alert-info fade-in" role="alert">
            Congratulazioni! Hai ottenuto uno sconto extra del 10%! Usa il codice: SPECIAL10
        </div>
        '''
    )
    return response_html
@app.route('/api/shipping_progress', methods=['GET'])
def shipping_progress():
    user = current_user if current_user.is_authenticated else None
    cart_total = 0

    if user:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user.id)})
        for item in user_data.get('cart', []):
            product = mongo.db.product.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                price = product['price'] - product.get('discount', 0)
                cart_total += item['quantity'] * price
    else:
        cart = get_guest_cart()
        for item in cart:
            product = mongo.db.product.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                price = product['price'] - product.get('discount', 0)
                cart_total += item['quantity'] * price

    shipping_threshold = 40  
    amount_remaining = max(0, shipping_threshold - cart_total)
    progress_percentage = min(100, (cart_total / shipping_threshold) * 100)

    
    response_html = render_template_string(
        '''
        <div id="shipping-progress-section" class="free-shipping-section">
            <span id="shipping-text">Spedizione gratuita per ordini superiori a 40€. Mancano: €{{ amount_remaining }}</span>
            <div class="progress-container">
                <div class="progress-bar-custom" id="progress-bar" style="width: {{ progress_percentage }}%;"></div>
            </div>
        </div>
        ''',
        amount_remaining=amount_remaining,
        progress_percentage=progress_percentage
    )

    return response_html, 200

@app.route('/api/shipping_progress_text', methods=['GET'])
def shipping_progress_text():
    user = current_user if current_user.is_authenticated else None
    cart_total = 0

    if user:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user.id)})
        for item in user_data.get('cart', []):
            product = mongo.db.product.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                price = product['price'] - product['discount'] if 'discount' in product and product['discount'] > 0 else product['price']
                cart_total += item['quantity'] * price
    else:
        cart = get_guest_cart()
        for item in cart:
            product = mongo.db.product.find_one({'_id': ObjectId(item['product_id'])})
            if product:
                price = product['price'] - product['discount'] if 'discount' in product and product['discount'] > 0 else product['price']
                cart_total += item['quantity'] * price

    shipping_threshold = 40  # Soglia per la spedizione gratuita
    amount_needed = max(0, shipping_threshold - cart_total)

    response_html = render_template_string(
        '''
        <p id="progress-text">Spedizione gratuita per ordini superiori a 40€. Mancano: €<span id="amount-needed">{{ amount_needed }}</span></p>
        ''',
        amount_needed=amount_needed
    )

    return response_html, 200
@app.route('/api/discount_timer/<product_id>', methods=['GET'])
def discount_timer(product_id):
    product = mongo.db.product.find_one({"_id": ObjectId(product_id)})
    if not product:
        return "Product not found", 404

    discount_end_date = product.get('discount_end_date')
    if not discount_end_date:
        return "No discount available", 400

    current_time = datetime.datetime.utcnow()
    time_left = discount_end_date - current_time

    if time_left.total_seconds() <= 0:
        return "<div class='alert alert-danger'>Offerta scaduta</div>", 200

    days = time_left.days
    hours, remainder = divmod(time_left.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)

    response_html = render_template_string(
        '''
        <div class="alert alert-danger">
            <p>Offerta valida per altre:</p>
            <div>{{ days }}d {{ hours }}h {{ minutes }}m {{ seconds }}s</div>
        </div>
        ''',
        days=days, hours=hours, minutes=minutes, seconds=seconds
    )

    return response_html


@app.route('/search_suggestions', methods=['GET'])
def search_suggestions():
    query = request.args.get('query', '')
    suggestions = []

    if query:
        suggestions = list(products_collection.find({'name': {'$regex': query, '$options': 'i'}}).limit(5))
        for suggestion in suggestions:
            suggestion['_id'] = str(suggestion['_id'])
    
    if suggestions:
        suggestions_html = render_template_string(
            '''
            {% for suggestion in suggestions %}
                <a href="#" 
                   hx-get="/auto_complete?query={{ suggestion.name }}" 
                   hx-target="#search-input" 
                   hx-swap="outerHTML" 
                   class="list-group-item list-group-item-action">{{ suggestion.name }}</a>
            {% endfor %}
            ''', suggestions=suggestions
        )
        return suggestions_html
    else:
        return ''

@app.route('/auto_complete', methods=['GET'])
def auto_complete():
    query = request.args.get('query', '')
    # Restituiamo un nuovo campo di input aggiornato con il suggerimento selezionato
    return f'<input class="form-control me-2 border-0" type="search" id="search-input" name="query" value="{query}" placeholder="Search" aria-label="Search" autocomplete="off" hx-get="/search_suggestions" hx-trigger="keyup changed delay:300ms" hx-target="#suggestions-container" hx-swap="innerHTML">'


@app.route('/toggle_filters', methods=['GET'])
def toggle_filters():
    # Ottieni il valore di 'is_visible' dalla richiesta; se non presente, assume 'false'
    is_visible = request.args.get('is_visible', 'false') == 'true'

    if is_visible:
        # Nascondi i filtri
        filters_html = ''
        button_text = "Mostra Filtri"
        new_is_visible = 'false'
    else:
      
        filters_html = '''
        <div class="filter-sidebar visible">
            <div class="d-flex justify-content-between align-items-center mb-3">
                <h5 class="mb-0">Filtra Prodotti</h5>
                <button class="btn-close" hx-get="/toggle_filters?is_visible=true" hx-target="#filter-section" hx-swap="outerHTML"></button>
            </div>
            <div class="filter-section">
                <label for="min-price" class="form-label">Prezzo minimo</label>
                <input type="number" class="form-control" id="min-price" name="min_price" placeholder="€0">
            </div>
            <div class="filter-section">
                <label for="max-price" class="form-label">Prezzo massimo</label>
                <input type="number" class="form-control" id="max-price" name="max_price" placeholder="€1000">
            </div>
            <div class="filter-section">
                <label for="color" class="form-label">Colore</label>
                <select class="form-select" id="color" name="color">
                    <option value="">Seleziona Colore</option>
                    <option value="rosso">Rosso</option>
                    <option value="blu">Blu</option>
                    <option value="verde">Verde</option>
                    <option value="giallo">Giallo</option>
                    <option value="nero">Nero</option>
                    <option value="bianco">Bianco</option>
                    <option value="arancione">Arancione</option>
                    <option value="viola">Viola</option>
                    <option value="celeste">Celeste</option>
                    <option value="grigio">Grigio</option>
                    <option value="marrone">Marrone</option>
                </select>
            </div>
            <div class="filter-section">
                <label for="size" class="form-label">Taglia</label>
                <select class="form-select" id="size" name="size">
                    <option value="">Seleziona Taglia</option>
                    <option value="S">S</option>
                    <option value="M">M</option>
                    <option value="L">L</option>
                    <option value="XL">XL</option>
                </select>
            </div>
            <div class="filter-section">
                <label for="category" class="form-label">Categoria</label>
                <select class="form-select" id="category" name="category">
                    <option value="">Seleziona Categoria</option>
                    <option value="Magliette">Magliette</option>
                    <option value="Sacche di tela">Sacche di tela</option>
                    <option value="Calzini">Calzini</option>
                    <option value="Cappelli">Cappelli</option>
                    <option value="Felpe">Felpe</option>
                </select>
            </div>
            <button class="btn btn-primary mt-3" 
                    hx-get="/api/products" 
                    hx-target="#search-results" 
                    hx-swap="innerHTML" 
                    hx-include="[name='min_price'], [name='max_price'], [name='color'], [name='size'], [name='category']"
                    hx-on="htmx:afterOnLoad: 
                        document.querySelector('.filter-sidebar').classList.remove('visible');
                        document.querySelector('#toggle-filters-button').innerText = 'Mostra Filtri';">
                Applica Filtri
            </button>
        </div>
        '''
        button_text = "Nascondi Filtri"
        new_is_visible = 'true'

    return render_template_string(f'''
    <div id="filter-section">
        <div id="filter-sidebar-container">
            {filters_html}
        </div>
        <button class="btn btn-filter-toggle mb-4" id="toggle-filters-button" hx-get="/toggle_filters?is_visible={new_is_visible}" hx-target="#filter-section" hx-swap="outerHTML"> 
            {button_text} 
        </button>
    </div>
    ''')




@app.route('/api/products', methods=['GET'])
def get_filtered_products():
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    color = request.args.get('color')
    size = request.args.get('size')
    category = request.args.get('category')

    query = {}

    if min_price is not None and min_price != '':
        query['price'] = {'$gte': min_price}
    if max_price is not None and max_price != '':
        if 'price' in query:
            query['price']['$lte'] = max_price
        else:
            query['price'] = {'$lte': max_price}
    if color:
        query['color'] = color
    if size:
        query['sizes'] = size
    if category:
        query['category'] = category

    # Log per vedere quale query viene inviata
    print("Query MongoDB:", query)

    products = list(products_collection.find(query))
    for product in products:
        product['_id'] = str(product['_id'])
        if product.get('discount', 0) > 0:
            product['original_price'] = product['price']
            product['price'] = product['price'] - product['discount']

    
    if request.headers.get('HX-Request') == 'true':
        return render_template('partials/product_grid.html', products=products)

    
    user_id = session.get('user_id')
    cart_item_count = get_cart_item_count(user_id)

    if request.args.get('from') == 'search':
        return render_template('search_results.html', products=products, cart_item_count=cart_item_count)
    else:
        return render_template('index.html', products=products, cart_item_count=cart_item_count)

class CheckoutForm(FlaskForm):
    name = StringField('Nome Completo', validators=[DataRequired()])
    address = StringField('Indirizzo', validators=[DataRequired()])
    city = StringField('Città', validators=[DataRequired()])
    country = StringField('Paese', validators=[DataRequired()])
    postal_code = StringField('CAP', validators=[DataRequired()])
    card_number = StringField('Numero di Carta', validators=[DataRequired(), Regexp(r'\d{16}', message="Il numero di carta deve essere composto da 16 cifre.")])
    expiry_date = StringField('Data di Scadenza (MM/YY)', validators=[DataRequired(), Regexp(r'\d{2}/\d{2}', message="Inserisci una data nel formato MM/YY.")])
    cvv = StringField('CVV', validators=[DataRequired(), Regexp(r'\d{3}', message="Il CVV deve essere composto da 3 cifre.")])
    submit = SubmitField('Effettua Ordine')

@app.route('/user_orders', methods=['GET'])
def user_orders():
    
    user_id = session.get('user_id')
    
    if not user_id:
        
        flash('Devi essere loggato per visualizzare i tuoi ordini.', 'danger')
        return redirect(url_for('login'))
    
    
    app.logger.info(f"Recupero ordini per l'utente con ID: {user_id}")
    
   
    orders_cursor = mongo.db.orders.find({'user_id': user_id}).sort('created_at', -1)
    
   
    orders = list(orders_cursor)
    app.logger.info(f"Numero di ordini trovati: {len(orders)}")
    
    
    cart_item_count = get_cart_item_count(user_id)
    
    # Renderizza la pagina degli ordini
    return render_template('user_orders.html', orders=orders, cart_item_count=cart_item_count)

@app.route('/continue_as_guest', methods=['GET'])
def continue_as_guest():
    
    return '<div></div>', 200  


def get_best_sellers(category=None, limit=3):
    query = {}
    if category:
        query['category'] = category
  
    best_sellers = list(mongo.db.product.find(query).sort('purchases', -1).limit(limit))
    return best_sellers

def calculate_cart_total():
    cart = session.get('cart', [])
    subtotal = 0

    for item in cart:
        
        subtotal += item['price'] * item['quantity']
    
    return subtotal



@app.route('/reviews/<review_id>', methods=['DELETE'])
@login_required
def delete_review(review_id):
    try:
        # Log the attributes of current_user
        app.logger.info(f"Current user object: {dir(current_user)}")

        review = mongo.db.reviews.find_one({'_id': ObjectId(review_id)})
        if not review:
            return '<div hx-swap-oob="true" class="alert alert-danger" role="alert">Recensione non trovata.</div>', 404

       
        if str(review['user_id']) != str(current_user.get_id()):
            return '<div hx-swap-oob="true" class="alert alert-danger" role="alert">Non sei autorizzato a eliminare questa recensione.</div>', 403

        
        mongo.db.reviews.delete_one({'_id': ObjectId(review_id)})

        # Recupera tutte le recensioni del prodotto
        product_reviews = list(mongo.db.reviews.find({'product_id': review['product_id']}))

        
        return render_template('reviews.html', reviews=product_reviews), 200
    except Exception as e:
        app.logger.error(f"Errore durante l'eliminazione della recensione: {str(e)}")
        return '<div hx-swap-oob="true" class="alert alert-danger" role="alert">Errore nel tentativo di eliminare la recensione.</div>', 500


@app.route('/apply_discount', methods=['POST'])
def apply_discount():
    user_id = session.get('user_id', 'guest')
    user_data = None
    discount_code_applied = False
    discount_amount = 0
    valid_discount_code = "WELCOME10"
    discount_percentage = 0.10

    
    if user_id == 'guest':
        cart = get_guest_cart()
    else:
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        cart = user_data['cart'] if user_data and 'cart' in user_data else []

    if not cart:
        flash('Il tuo carrello è vuoto. Aggiungi prodotti prima di applicare un codice sconto.', 'danger')
        return redirect(url_for('checkout'))

    # Applica il codice sconto se valido
    discount_code = request.form.get('discount_code', '').strip()
    if discount_code == valid_discount_code:
        discount_code_applied = True

   
    subtotal = sum(item['price'] * item['quantity'] for item in cart)
    discount_amount = subtotal * discount_percentage if discount_code_applied else 0
    total = subtotal - discount_amount
    shipping_cost = 0 if subtotal >= 40 else 5
    total += shipping_cost

   
    cart_item_count = sum(item['quantity'] for item in cart)

    
    return render_template(
        'order_summary.html',  
        cart=cart,
        subtotal=subtotal,
        discount_amount=discount_amount,
        total=total,
        shipping_cost=shipping_cost,
        cart_item_count=cart_item_count,
        discount_code_applied=discount_code_applied
    )




@app.route('/flash_sale_products', methods=['GET'])
def flash_sale_products():
    page = int(request.args.get('page', 1))
    print(f"Ricevuta richiesta per la pagina: {page}")  

    per_page = 3
    skip = (page - 1) * per_page
    flash_sale_products = list(products_collection.find({'discount': {'$gt': 0}}).skip(skip).limit(per_page))

    total_products = products_collection.count_documents({'discount': {'$gt': 0}})
    total_pages = (total_products // per_page) + (1 if total_products % per_page > 0 else 0)
    
    prev_page = max(1, page - 1)
    next_page = min(total_pages, page + 1)

    for product in flash_sale_products:
        product['_id'] = str(product['_id'])
        if product.get('discount', 0) > 0:
            product['original_price'] = product['price']
            product['price'] = product['price'] - (product['price'] * product['discount'] / 100)

    print(f"Risposta: Pagina corrente {page}, Pagina successiva {next_page}, Totale pagine {total_pages}")

    return render_template('partials/flash_sale_products.html', 
                            flash_sale_products=flash_sale_products, 
                            prev_page=prev_page, 
                            next_page=next_page, 
                            current_page=page,
                            total_pages=total_pages)



@app.route('/api/load_more_products', methods=['GET'])
def load_more_products():
    current_page = int(request.args.get('current_page', 1))
    per_page = 8 
    skip_count = current_page * per_page  

   
    products = list(mongo.db.product.find().skip(skip_count).limit(per_page))

    best_sellers = get_best_sellers()
    best_seller_ids = {str(product['_id']) for product in best_sellers}

    
    for product in products:
        product['_id'] = str(product['_id'])
        product['is_best_seller'] = product['_id'] in best_seller_ids
        if product.get('discount', 0) > 0:
            product['original_price'] = product['price']
            product['price'] = product['price'] - (product['price'] * product['discount'] / 100)

  
    total_products = mongo.db.product.count_documents({})
    has_more_products = (skip_count + per_page) < total_products

   
    rendered_products = render_template('product_partial.html', products=products)

    
    if has_more_products:
        button_html = f'''
        <button id="load-more-button" class="btn btn-outline-dark" 
                hx-get="/api/load_more_products?current_page={current_page + 1}"
                hx-target="#product-list"
                hx-swap="beforeend"
                hx-push-url="false">
            Carica altro
        </button>
        '''
        
        return f'{rendered_products}<div hx-swap-oob="true" id="load-more-container">{button_html}</div>'
    else:
       
        return f'{rendered_products}<div hx-swap-oob="true" id="load-more-container" style="display: none;"></div>'



if __name__ == '__main__':
    app.run(debug=True)