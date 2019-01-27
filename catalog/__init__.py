from flask import Flask, render_template, request
from flask import redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_category import Base, Category, Item, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Item Catalog Application"


# Connect to Database and create database session
engine = create_engine('sqlite:///Categories.db',
                       connect_args={'check_same_thread': False},
                       echo=True)
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()


# Create anti-forgery state token
@app.route('/login')
def showLogin():
    state = ''.join(random.choice(string.ascii_uppercase + string.digits)
                    for x in xrange(32))
    login_session['state'] = state
    # return "The current session state is %s" % login_session['state']
    gconnect()
    return render_template('login.html', STATE=state)


@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validate state token
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('Invalid state parameter.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # Obtain authorization code
    code = request.data

    try:
        # Upgrade the authorization code into a credentials object
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Failed to upgrade the authorization code.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Check that the access token is valid.
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    result = json.loads(h.request(url, 'GET')[1])
    # If there was an error in the access token info, abort.
    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is used for the intended user.
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token's user ID doesn't match given user ID."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Verify that the access token is valid for this app.
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token's client ID does not match app's."), 401)
        print ("Token's client ID does not match app's.")
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response =
        make_response(json.dumps('Current user is already connected.'),
                      200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # Store the access token in the session for later use.
    login_session['access_token'] = credentials.access_token
    login_session['gplus_id'] = gplus_id

    # Get user info
    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': credentials.access_token, 'alt': 'json'}
    answer = requests.get(userinfo_url, params=params)

    data = answer.json()

    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']


# see if user exists, if not make a new one
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    output = ''
    output += '<h1>Welcome, '
    output += login_session['username']
    output += '!</h1>'
    output += '<img src="'
    output += login_session['picture']
    output += ' " style = "width: 300px; height: 300px;border-radius:'
    output += '150px;-webkit-border-radius: 150px;-moz-border-radius: 150px;">'
    flash("you are now logged in as %s" % login_session['username'])
    print ("done!")
    return output


# DISCONNECT - Revoke a current user's token and reset their login_session
@app.route('/disconnect')
def disconnect():
    gdisconnect()
    login_session.clear()
    flash("You have successfully been logged out.")
    return redirect(url_for('showCategories'))


@app.route('/gdisconnect')
def gdisconnect():
    access_token = login_session['access_token']
    print ('In gdisconnect access token is %s', access_token)
    print ('User name is: ')
    print (login_session['username'])
    if access_token is None:
        print 'Access Token is None'
        response =
        make_response(json.dumps('Current user not connected.'),
                      401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = ('https://accounts.google.com/o/oauth2/revoke?token=%s'
           % login_session['access_token'])
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    print 'result is '
    print result
    if result['status'] == '200':
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        response = make_response(json.dumps('Successfully disconnected.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        response =
        make_response(json.dumps('Failed to revoke token for given user.',
                      400))
        response.headers['Content-Type'] = 'application/json'
        return response


# JSON APIs to view Category Information
@app.route('/category/<int:category_id>/item/JSON')
def categoryJSON(category_id):
    category = session.query(Category).filter_by(id=category_id).one()
    items = session.query(Item).filter_by(
        category_id=category_id).all()
    return jsonify(Items=[i.serialize for i in items])


@app.route('/category/<int:category_id>/item/<int:item_id>/JSON')
def ItemJSON(category_id, item_id):
    Item = session.query(Item).filter_by(id=item_id).one()
    return jsonify(Item=Item.serialize)


@app.route('/category/JSON')
def categoriesJSON():
    categories = session.query(Category).all()
    return jsonify(categories=[r.serialize for r in categories])


# Show all categories
@app.route('/')
@app.route('/category/')
def showCategories():
    categories = session.query(Category).order_by(asc(Category.name))
    return render_template('Catalog.html', categories=categories)
# Create a new category


@app.route('/category/new/', methods=['GET', 'POST'])
def newCategory():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        catname = request.form['name']
        if catname:
            exists = session.query(Category).filter_by(
                     name=request.form['name']).first()
            if not exists:
                newCategory = Category(
                    name=request.form['name'],
                    user_id=login_session['user_id'])
                session.add(newCategory)
                flash('New Category %s Successfully Created'
                      % newCategory.name)
                session.commit()
            else:
                flash('Category already Exists')
        else:
            flash('New Category Cannot be Null')
        return redirect(url_for('showCategories'))
    else:
        return render_template('newCategory.html')

# Edit a category


@app.route('/category/<category_name>/edit/', methods=['GET', 'POST'])
def editCategory(category_name):
    if 'username' not in login_session:
        return redirect('/login')
    editedCategory = session.query(
        Category).filter_by(name=category_name).one()
    if request.method == 'POST':
        if request.form['name']:
            exists = session.query(Category).filter_by(
                     name=request.form['name']).first()
            if not exists:
                editedCategory.name = request.form['name']
                flash('Category Successfully Edited %s' % editedCategory.name)
            else:
                flash('Category Name Already Exists')
        return redirect(url_for('showCatalog'))

    else:
        return render_template('editCategory.html', category=editedCategory)


# Delete a category
@app.route('/category/<category_name>/delete/', methods=['GET', 'POST'])
def deleteCategory(category_name):
    if 'username' not in login_session:
        return redirect('/login')
    categoryToDelete = session.query(
        Category).filter_by(name=category_name).one()
    if request.method == 'POST':
        session.delete(categoryToDelete)
        flash('%s Successfully Deleted' % categoryToDelete.name)
        session.commit()
        return redirect(url_for('showCategories', category_name=category_name))
    else:
        return render_template('deleteCategory.html',
                               category=categoryToDelete)


# Show a category item
@app.route('/category/<category_name>/item/')
def showCatalog(category_name):
    category = session.query(Category).filter_by(name=category_name).one()
    categories = session.query(Category).all()
    items = session.query(Item).filter_by(category_id=category.id).all()
    return render_template('catalog.html', Category=category, items=items,
                           category_name=category.name, categories=categories)


# Display Items
@app.route('/category/<category_name>/<item_name>/')
def showItem(category_name, item_name):
    category = session.query(Category).filter_by(name=category_name).one()
    item = session.query(Item).filter_by(
                                         category_id=category.id,
                                         name=item_name).one()
    categories = session.query(Category).all()
    return render_template('Item.html', item=item,
                           category_name=category.name)


# Create a new item item
@app.route('/category/<category_name>/items/new/', methods=['GET', 'POST'])
def newItem(category_name):
    if 'username' not in login_session:
        return redirect('/login')
    category = session.query(Category).filter_by(name=category_name).one()
    if request.method == 'POST':
        catname = request.form['name']
        if catname:
            catname = request.form.get('name')
            newItem = Item(name=request.form['name'],
                           description=request.form['description'],
                           category_id=category.id,
                           user_id=login_session['user_id'])
            session.add(newItem)
            session.commit()
            flash('New Catalog (%s) Item Successfully Created'
                  % (newItem.name))
        else:
            flash('Catalog Name Cannot be Null')
        return redirect(url_for('showCatalog', category_name=category_name))
    else:
        return render_template('newItem.html', category_name=category_name)

# Edit a item item


@app.route('/category/<category_name>/<item_name>/edit',
           methods=['GET', 'POST'])
def editItem(category_name, item_name):
    if 'username' not in login_session:
        return redirect('/login')
    editedItem = session.query(Item).filter_by(name=item_name).one()
    if editedItem.user_id != login_session['user_id']:
        flash('You are not allowed to edit this catalog items')
        return render_template('editItem.html',
                               category_name=category_name,
                               item_name=item_name,
                               item=editedItem)
    category = session.query(Category).filter_by(name=category_name).one()
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        session.add(editedItem)
        session.commit()
        flash('Item Successfully Edited')
        return redirect(url_for('showCatalog', category_name=category_name))
    else:
        return render_template('editItem.html',
                               category_name=category_name,
                               item_name=item_name,
                               item=editedItem)


# Delete a item item
@app.route('/category/<category_name>/<item_name>/delete',
           methods=['GET', 'POST'])
def deleteItem(category_name, item_name):
    if 'username' not in login_session:
        return redirect('/login')
    category = session.query(Category).filter_by(name=category_name).one()
    itemToDelete = session.query(Item).filter_by(name=item_name).one()
    if itemToDelete.user_id != login_session['user_id']:
        flash('You are not allowed to delete this catalog items')
        return redirect(url_for('showCatalog', category_name=category_name))
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('Item Successfully Deleted')
        return redirect(url_for('showCatalog', category_name=category_name))
    else:
        return render_template('deleteItem.html', item=itemToDelete)


# JSON APIs to view Catalog Information
@app.route('/catalog.json')
def catalogJSON():
    # returns all categories with their items
    items = session.query(Item).order_by(Item.category_id.asc(), Item.id.asc())
    categories = session.query(Category).order_by(Category.id.asc())
    return jsonify(CatalogItems=[i.serialize for i in items])


def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id


def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user


def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None

if __name__ == '__main__':
    app.secret_key = 'Not_so_so_secret'
    app.debug = True
    app.run(host='0.0.0.0', port=5000)
