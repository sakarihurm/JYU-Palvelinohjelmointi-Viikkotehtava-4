import os
from flask import Flask, request, Response, render_template, url_for, redirect, session
import firebase_admin
from firebase_admin import firestore
from authlib.integrations.flask_client import OAuth
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

app.config["SECRET_KEY"] = os.environ["SECRET_KEY"]

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

CONF_URL = 'https://accounts.google.com/.well-known/openid-configuration'
oauth = OAuth(app)
oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url=CONF_URL,
    client_kwargs={
        'scope': 'openid email profile',
        'prompt': 'consent'
    }
)

firebase_admin.initialize_app()
db = firestore.client()

@app.route('/')
def homepage():

    if session.get('kirjautunut'):
        tarkistaKayttaja()

    kilpailut_stream = []
    # Haetaan kaikki kilpailut
    for doc in db.collection("kilpailut").stream():
        kilpailu = doc.to_dict()
        kilpailu["id"] = doc.id
        kilpailut_stream.append(kilpailu)

    kilpailut = []
    # Otetaan talteen vain kilpailun id, nimi ja alkuaika
    for kilpailu in kilpailut_stream:
        kilpailut.append((kilpailu["id"], kilpailu["nimi"], kilpailu["alkuaika"]))
    
    return Response(render_template("etusivu.xhtml", 
                                    kilpailut=kilpailut, 
                                    omistajan_nimi=session.get('user_name'), 
                                    kirjautunut=session.get('kirjautunut')), 
                                    content_type="application/xhtml+xml; charset=utf-8")

def tarkistaKayttaja():
    # Haetaan kaikki omistajien sähköpostit
    omistajat = [
        doc.to_dict()["omistajat"]
        for doc in db.collection("joukkueet").stream()
    ]
    # Tarkistetaan löytyykö sähköposti jo omistajista
    for sposti in omistajat:
        if session['email'] in sposti:
            return
    # Jos sähköpostia ei löydy, lisätään se omistajaksi testidataan
    db.collection("joukkueet").document("730129").update({
        "omistajat": firestore.ArrayUnion([session["email"]])
    })
    db.collection("joukkueet").document("4685099566104576").update({
        "omistajat": firestore.ArrayUnion([session["email"]])
    })
    db.collection("joukkueet").document("5238782968201216").update({
        "omistajat": firestore.ArrayUnion([session["email"]])
    })

@app.route('/kilpailu', methods=['POST', 'GET'])
def kilpailu():

    # Otetaan talteen kilpailun id ja nimi
    kilpailuid = int(request.values.get("id", 0))
    kilpailun_nimi = request.values.get("nimi", "") + " " + request.values.get("alkuaika", "")

    # Haetaan sarjat, jotka kuuluvat kilpailuun
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

    # Haetaan joukkueet
    joukkueet = [
        doc.to_dict()
        for doc in db.collection("joukkueet").stream()
    ]

    suodatetut_joukkueet = []
    # Lisätään järjestetyt jäsenet, nimi ja sarja helpompaan muotoon
    for joukkue in joukkueet:
        suodatetut_joukkueet.append((joukkue["nimi"], 
                                    sorted(joukkue["jasenet"]),
                                    joukkue["sarja"]))
    # Järjestetään joukkueet nimen mukaan
    suodatetut_joukkueet = sorted(suodatetut_joukkueet, key=lambda x: x[0].lower())
        
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
        # Jos käyttäjä ei ole kirjautunut, ohjataan kirjautumissivulle
        return redirect(url_for('login'))

    # Haetaan kaikki joukkueet, jotka kirjautunut käyttäjä omistaa
    joukkueet = [
        doc.to_dict()
        for doc in db.collection("joukkueet")
                    .where("omistajat", "array_contains", session["email"])
                    .stream()
    ]

    # Haetaan kaikki sarjat
    sarjat = {
        doc.id: doc.to_dict()
        for doc in db.collection("sarjat").stream()
    }

    # Haetaan kaikki kilpailut
    kilpailut = {
        doc.id: doc.to_dict()
        for doc in db.collection("kilpailut").stream()
    }

    tulos = {}

    for joukkue in joukkueet:
        # Otetaan joukkueen sarja talteen
        sarja = sarjat[str(joukkue["sarja"])]
        # Otetaan sarjan kilpailu talteen
        kilpailu = kilpailut[str(sarja["kilpailu"])]

        # Otetaan kilpailun id, johon joukkue kuuluu
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
            "jasenet": sorted(joukkue["jasenet"]) # Järjestetään joukkueen jäsenet
        })

    # Järjestetään kilpailun sarjat nimen mukaan
    for kilpailu in tulos.values():
        kilpailu["sarjat"] = dict(
            sorted(
                kilpailu["sarjat"].items(),
                key=lambda x: x[0].lower()
            )
        )
    # Järjestetään kilpailun joukkueet nimen mukaan sarjoittain
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
    # Otetaan tiedot talteen, kun lisää joukkue -painiketta painetaan
    kilpailun_nimi = request.values.get("kilpailu", "")
    kilpailun_id = request.values.get("kilpailuid", "")
    sarjan_nimi = request.values.get("sarja", "")

    # Avataan joukkueen lisäys sivu
    return Response(render_template('muokkaa.xhtml', 
                            omistajan_nimi=session.get('user_name'),
                            kilpailun_nimi=kilpailun_nimi,
                            kilpailuid=kilpailun_id,
                            sarjan_nimi=sarjan_nimi,
                            virhe="",
                            kirjautunut=session.get('kirjautunut')),
                            content_type="application/xhtml+xml; charset=utf-8")

@app.route('/tallenna', methods=['POST', 'GET'])
def tallenna():

    # Otetaan lomakkeelta syötetyt tiedot talteen
    kilpailuid = int(request.values.get("kilpailuid", 0))
    kilpailun_nimi = request.values.get("kilpailun_nimi", "")
    sarjan_nimi = request.values.get("sarja", "")
    joukkue = request.form.get("joukkueen_nimi", "").strip()
    jasenet = request.form.getlist('jasen')

    # Suodatetaan tyhjät jäsenten kentät pois
    jasenet = [j.strip() for j in jasenet if j.strip()]

    # Tarkistetaan syötetyt tiedot
    if tarkistaJoukkue(joukkue) == False:
        return Response(render_template('muokkaa.xhtml', 
                            omistajan_nimi=session.get('user_name'),
                            kilpailun_nimi=kilpailun_nimi,
                            kilpailuid=kilpailuid,
                            sarjan_nimi=sarjan_nimi,
                            virhe=session['tallennusvirhe'],
                            kirjautunut=session.get('kirjautunut')),
                            content_type="application/xhtml+xml; charset=utf-8")
    if tarkistaJasenet(jasenet) == False:
        return Response(render_template('muokkaa.xhtml', 
                            omistajan_nimi=session.get('user_name'),
                            kilpailun_nimi=kilpailun_nimi,
                            kilpailuid=kilpailuid,
                            sarjan_nimi=sarjan_nimi,
                            virhe=session['tallennusvirhe'],
                            kirjautunut=session.get('kirjautunut')),
                            content_type="application/xhtml+xml; charset=utf-8")
    
    # Haetaan sarjan id, sarjan nimen perusteella
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

    # Lisätään annetut tiedot uuteen joukkueeseen
    joukkue = {
        "nimi": joukkue,
        "sarja": sarja_id,
        "jasenet": jasenet,
        "omistajat": [session["email"]],
        "tulospalvelu": []
    }

    # Lisätään uusi joukkue firestoreen
    db.collection("joukkueet").add(joukkue)

    return redirect(url_for('joukkueet'))

# Tarkistetaan joukkueen nimi, palautetaan false jos ilmenee virhe
def tarkistaJoukkue(joukkue):
    joukkueen_nimi = joukkue.lower().strip()

    if len(joukkueen_nimi) == 0:
        session['tallennusvirhe'] = "Virhe: joukkueen nimi ei saa olla tyhjä."
        return False

    joukkueiden_nimet = [
        doc.to_dict()["nimi"]
        for doc in db.collection("joukkueet").stream()
    ]

    for nimi in joukkueiden_nimet:
        if nimi.strip().lower() == joukkueen_nimi:
            session['tallennusvirhe'] = "Virhe: joukkue on jo olemassa."
            return False
    return True

# Tarkistetaan joukkueen jasenet, palautetaan false jos ilmenee virhe
def tarkistaJasenet(jasenet):
    jasenet_sorted = []
    for jasen in jasenet:
        jasenet_sorted.append(jasen.lower())

    if len(jasenet_sorted) < 2 or len(jasenet_sorted) > 5: 
        session['tallennusvirhe'] = "Virhe: jäseniä liian vähän tai liikaa."
        return False
    
    if len(jasenet_sorted) != len(set(jasenet_sorted)):
        session['tallennusvirhe'] = "Virhe: jäsen on jo olemassa."
        return False
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