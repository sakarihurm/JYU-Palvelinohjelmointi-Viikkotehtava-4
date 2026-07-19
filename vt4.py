from flask import Flask, request, Response, render_template, url_for, redirect, session
import json, hashlib, sqlite3, secrets

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


@app.route('/')
def homepage():
    user = session.get('user')
    return Response(render_template("etusivu.xhtml", 
                                    kilpailut=[], 
                                    omistajan_nimi=user, 
                                    kirjautunut=False), 
                                    content_type="application/xhtml+xml; charset=utf-8")


@app.route('/login')
def login():
    redirect_uri = url_for('auth', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth')
def auth():
    token = oauth.google.authorize_access_token()
    session['user'] = token['userinfo']
    email = session['user']['email']
    return redirect('/')


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/')