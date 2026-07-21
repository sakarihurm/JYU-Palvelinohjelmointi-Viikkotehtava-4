from flask import Flask, request, Response, render_template, url_for, redirect, session
import json, hashlib, sqlite3, secrets, firebase_admin
from firebase_admin import firestore, credentials
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)
app.secret_key = '!secret'
app.config.from_object('config')
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
oauth = OAuth(app)
oauth.register(
    name='google',
    server_metadata_url=CONF_URL,
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'consent'
    }
)

cred = credentials.Certificate(r'C:\Users\sakar\Desktop\palvelinohj\vt4\ties4080-ohjaus4-479214-58e499245f10.json')
firebase_admin.initialize_app(cred)
db = firestore.client()

@app.route('/')
def homepage():
    user = session.get('user')

    kilpailut_stream = []

    for doc in db.collection("kilpailut").stream():
        kilpailu = doc.to_dict()
        kilpailu["id"] = doc.id
        kilpailut_stream.append(kilpailu)

    kilpailut = []
    for kilpailu in kilpailut_stream:
        kilpailut.append((kilpailu["id"], kilpailu["nimi"], kilpailu["alkuaika"]))
    
    return Response(render_template("etusivu.xhtml", 
                                    kilpailut=kilpailut, 
                                    omistajan_nimi=session.get('user_name'), 
                                    kirjautunut=session.get('kirjautunut')), 
                                    content_type="application/xhtml+xml; charset=utf-8")


@app.route('/kilpailu', methods=['POST', 'GET'])
def kilpailu():

    # Otetaan talteen kilpailun id ja nimi
    kilpailuid = int(request.values.get("id", 0))
    kilpailun_nimi = request.values.get("nimi", "") + " " + request.values.get("alkuaika", "")

    sarjat = [
    doc.to_dict()
    for doc in db.collection("sarjat")
                .where("kilpailu", "==", 6050225628119040)
                .stream()
    ]

    sarjat = sorted(sarjat, key=lambda x: x["nimi"].lower()) # Järjestetään sarjat nimen mukaan
    
    suodatetut_sarjat = []

    for sarja in sarjat:
        suodatetut_sarjat.append((sarja["sid"], sarja["nimi"]))
    
    joukkueet = [
    doc.to_dict()
    for doc in db.collection("joukkueet").stream()
    ]

    suodatetut_joukkueet = []
    for joukkue in joukkueet:
        suodatetut_joukkueet.append((joukkue["nimi"], 
                                    sorted(joukkue["jasenet"]),
                                    joukkue["sarja"]))
        
    return Response(render_template('joukkueet.xhtml', 
                                    joukkueet=suodatetut_joukkueet, 
                                    suodatetut_sarjat=suodatetut_sarjat, 
                                    kilpailun_nimi=kilpailun_nimi, 
                                    omistajan_nimi=session.get('user_name'), 
                                    kirjautunut=session.get('kirjautunut')), 
                                    content_type="application/xhtml+xml; charset=utf-8")


@app.route('/login')
def login():
    redirect_uri = url_for('auth', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth')
def auth():
    token = oauth.google.authorize_access_token()
    session['user'] = token['userinfo']
    print(session.get('user'))
    email = session['user']['email']
    session['user_name'] = session['user']['given_name'] + " " + session['user']['family_name']
    session['kirjautunut'] = True
    return redirect('/')


@app.route('/logout')
def logout():
    session.pop('user', None)
    session['kirjautunut'] = False
    return redirect('/')