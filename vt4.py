from flask import Flask, request, Response, render_template, url_for, redirect, session
import firebase_admin
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
                .where("kilpailu", "==", kilpailuid)
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


@app.route('/joukkueet', methods=['POST', 'GET'])
def joukkueet():
    if not session.get('kirjautunut'):
        return redirect(url_for('login'))

    joukkueet = [
        doc.to_dict()
        for doc in db.collection("joukkueet")
                    .where("omistajat", "array_contains", session["email"])
                    .stream()
    ]

    sarjat = {
        doc.id: doc.to_dict()
        for doc in db.collection("sarjat").stream()
    }

    kilpailut = {
        doc.id: doc.to_dict()
        for doc in db.collection("kilpailut").stream()
    }

    tulos = {}

    for joukkue in joukkueet:
        sarja = sarjat[str(joukkue["sarja"])]
        kilpailu = kilpailut[str(sarja["kilpailu"])]

        kilpailu_id = str(sarja["kilpailu"])

        # Luodaan kilpailu vain kerran
        if kilpailu_id not in tulos:
            tulos[kilpailu_id] = {
                "nimi": kilpailu["nimi"],
                "alkuaika": kilpailu["alkuaika"],
                "sarjat": {}
            }

        # Luodaan sarja vain kerran
        if sarja["nimi"] not in tulos[kilpailu_id]["sarjat"]:
            tulos[kilpailu_id]["sarjat"][sarja["nimi"]] = []

        # Lisätään joukkue
        tulos[kilpailu_id]["sarjat"][sarja["nimi"]].append({
            "nimi": joukkue["nimi"],
            "jasenet": sorted(joukkue["jasenet"])
        })

    for kilpailu in tulos.values():
        kilpailu["sarjat"] = dict(
            sorted(
                kilpailu["sarjat"].items(),
                key=lambda x: x[0].lower()
            )
        )
    for kilpailu in tulos.values():
        for joukkueet in kilpailu["sarjat"].values():
            joukkueet.sort(key=lambda j: j["nimi"].lower())

    return Response(render_template('omistaja.xhtml', 
                                omistajan_nimi=session.get('user_name'), 
                                omistajan_sposti=session.get('email'), 
                                kilpailut=tulos, 
                                kirjautunut=session.get('kirjautunut')), 
                                content_type="application/xhtml+xml; charset=utf-8")

@app.route('/lisaaJoukkue', methods=['POST', 'GET'])
def lisaaJoukkue():
    kilpailun_nimi = request.values.get("kilpailu", "")
    kilpailun_id = request.values.get("kilpailuid", "")
    sarjan_nimi = request.values.get("sarja", "")
    virhe = request.args.get("virhe","")
    return Response(render_template('muokkaa.xhtml', 
                            omistajan_nimi=session.get('user_name'),
                            kilpailun_nimi=kilpailun_nimi,
                            kilpailuid=kilpailun_id,
                            sarjan_nimi=sarjan_nimi,
                            virhe=virhe,
                            kirjautunut=session.get('kirjautunut')),
                            content_type="application/xhtml+xml; charset=utf-8")

@app.route('/tallenna', methods=['POST', 'GET'])
def tallenna():
    kilpailuid = int(request.values.get("kilpailuid", 0))
    sarjan_nimi = request.values.get("sarja", "")
    joukkue = request.form.get("joukkueen_nimi", "").strip()
    jasenet = request.form.getlist('jasen')

    # Tarkistetaan syötetyt tiedot
    if tarkistaJoukkue(joukkue) == False:
        return redirect(url_for('lisaaJoukkue', virhe=session['tallennusvirhe']))
    if tarkistaJasenet(jasenet) == False:
        return redirect(url_for('lisaaJoukkue', virhe=session['tallennusvirhe']))

    docs = (
        db.collection("sarjat")
        .where("nimi", "==", sarjan_nimi)
        .where("kilpailu", "==", kilpailuid)
        .limit(1)
        .stream()
    )
    doc = next(docs, None)
    if doc:
        sarja_id = int(doc.id)
    else:
        sarja_id = 0

    joukkue = {
        "nimi": joukkue,
        "sarja": sarja_id,
        "jasenet": jasenet,
        "omistajat": [session["email"]],
        "tulospalvelu": []
    }


    db.collection("joukkueet").add(joukkue)

    return redirect(url_for('joukkueet'))


def tarkistaJoukkue(joukkue):
    joukkueen_nimi = joukkue.lower().strip()
    if len(joukkueen_nimi) == 0:
        session['tallennusvirhe'] = "Virhe: joukkueen nimi ei saa olla tyhjä."
        return False
    return True
    
def tarkistaJasenet(jasenet):
    jasenet_sorted = []
    for jasen in jasenet:
        jasenet_sorted.append(jasen.lower())

    if len(jasenet_sorted) < 2 or len(jasenet_sorted) > 5: 
        session['tallennusvirhe'] = "Virhe: jäseniä liian vähän tai liikaa."
        return False
    
    # if len(jasenet_sorted) != len(set(jasenet_sorted)):
    #     session['tallennusvirhe'] = "Virhe: jäsen on jo olemassa."
    #     return False
    return True

@app.route('/login')
def login():
    redirect_uri = url_for('auth', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route('/auth')
def auth():
    token = oauth.google.authorize_access_token()
    session['user'] = token['userinfo']
    session['email'] = session['user']['email']
    session['user_name'] = session['user']['given_name'] + " " + session['user']['family_name']
    session['kirjautunut'] = True
    return redirect('/')


@app.route('/logout')
def logout():
    session.pop('user', None)
    session.clear()
    return redirect('/')