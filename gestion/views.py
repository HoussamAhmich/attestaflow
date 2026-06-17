import os
import io
import json
from datetime import date
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.http import HttpResponse, JsonResponse
from django.core.mail import EmailMessage
from django.contrib.auth.models import User
from django.conf import settings
from .models import Utilisateur, Demande, Attestation, JournalAction, EtudiantDB


def journaliser(utilisateur, action, detail=''):
    try:
        JournalAction.objects.create(
            utilisateur=utilisateur,
            action=action,
            detail=detail
        )
    except Exception:
        pass


# 🔐 LOGIN
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            u_obj, _ = Utilisateur.objects.get_or_create(
                user=user,
                defaults={
                    'nom': user.username,
                    'email': user.email,
                    'mot_de_passe': '',
                    'role': 'beneficiaire'
                }
            )
            journaliser(u_obj, 'connexion', f"Connexion de {user.username}")
            return redirect('/dashboard/')
        else:
            return render(request, 'login.html', {
                'error': "Nom ou mot de passe incorrect"
            })
    return render(request, 'login.html')


# 🚪 LOGOUT
def logout_view(request):
    try:
        u_obj = Utilisateur.objects.get(user=request.user)
        journaliser(u_obj, 'deconnexion', f"Déconnexion de {request.user.username}")
    except:
        pass
    logout(request)
    return redirect('/login/')


# 🏠 HOME
def home(request):
    return redirect('/login/')


# 🏠 DASHBOARD
def dashboard(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        role = u.role
    except:
        role = "inconnu"
        u = None
    if u and role in ['agent', 'admin']:
        demandes = Demande.objects.all()
    else:
        demandes = Demande.objects.filter(utilisateur=u) if u else Demande.objects.none()
    return render(request, 'dashboard.html', {
        'user': request.user,
        'role': role,
        'demandes_recentes': demandes.order_by('-id')[:5],
        'total_demandes': demandes.count(),
        'en_attente': demandes.filter(statut='en attente').count(),
        'approuvees': demandes.filter(statut='acceptée').count(),
        'refusees': demandes.filter(statut='refusée').count(),
        'demandes_count': demandes.count(),
    })


# 📥 DEMANDE
def ajouter_demande(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        utilisateur = Utilisateur.objects.get(user=request.user)
    except Utilisateur.DoesNotExist:
        utilisateur = Utilisateur.objects.create(
            user=request.user,
            nom=request.user.username,
            email=request.user.email,
            mot_de_passe='',
            role="beneficiaire"
        )
    if utilisateur.role not in ['beneficiaire']:
        return render(request, '403.html', status=403)

    # Récupérer la dernière demande pour pré-remplir
    derniere_demande = Demande.objects.filter(utilisateur=utilisateur).order_by('-id').first()

    if request.method == "POST":
        matricule = request.POST.get('matricule', '').strip()
        type_document = request.POST.get('type_document', 'Attestation de scolarité')
        try:
            etudiant = EtudiantDB.objects.get(matricule=matricule)
        except EtudiantDB.DoesNotExist:
            return render(request, 'demande.html', {
                'error_matricule': 'Matricule introuvable ❌ — vérifiez votre matricule et réessayez.',
                'submitted_matricule': matricule,
                'user': request.user,
                'role': utilisateur.role,
                'demandes_count': Demande.objects.filter(utilisateur=utilisateur).count(),
            })
        Demande.objects.create(
            type_document=type_document,
            statut="en attente",
            utilisateur=utilisateur,
            cin=etudiant.cin,
            date_naissance=etudiant.date_naissance,
            lieu_naissance=etudiant.lieu_naissance,
            filiere=etudiant.filiere,
            niveau=etudiant.niveau,
            annee_universitaire=etudiant.annee_universitaire,
            matricule=etudiant.matricule,
        )
        utilisateur.nom = f"{etudiant.prenom} {etudiant.nom}"
        utilisateur.save()
        journaliser(utilisateur, 'soumission', f"Demande soumise par {utilisateur.nom}")

        # Email étudiant — confirmation de réception
        email_etudiant = getattr(etudiant, 'email', None) or utilisateur.email
        if email_etudiant:
            try:
                EmailMessage(
                    subject="Votre demande est en cours de traitement",
                    body=(
                        f"Bonjour {utilisateur.nom},\n\n"
                        f"Votre demande d'{type_document} a bien été reçue et est en cours de traitement.\n"
                        f"Vous recevrez une confirmation dès qu'elle sera traitée.\n\n"
                        f"Cordialement,\nAttestaFlow EMSI"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[email_etudiant],
                ).send()
            except Exception:
                pass

        # Email agents/admins — notification nouvelle demande
        agents = Utilisateur.objects.filter(role__in=['agent', 'admin'])
        emails_agents = [a.email for a in agents if a.email]
        if emails_agents:
            try:
                EmailMessage(
                    subject="Nouvelle demande d'attestation",
                    body=(
                        f"Une nouvelle demande d'{type_document} a été soumise "
                        f"par {utilisateur.nom}.\n"
                        f"Connectez-vous pour la traiter."
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=emails_agents,
                ).send()
            except Exception:
                pass

        return render(request, 'demande.html', {
            'success': True,
            'user': request.user,
            'role': utilisateur.role,
            'demandes_count': Demande.objects.filter(utilisateur=utilisateur).count(),
        })

    return render(request, 'demande.html', {
        'user': request.user,
        'role': utilisateur.role,
        'utilisateur': utilisateur,
        'derniere_demande': derniere_demande,
        'demandes_count': Demande.objects.filter(utilisateur=utilisateur).count(),
    })


# 📋 LISTE DEMANDES
def liste_demandes(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        role = u.role
    except:
        return redirect('/login/')
    if role in ['agent', 'admin']:
        demandes = Demande.objects.all()
    else:
        demandes = Demande.objects.filter(utilisateur=u)
    statut = request.GET.get('statut', '')
    recherche = request.GET.get('q', '')
    if statut == 'acceptée':
        demandes = demandes.filter(statut='acceptée').exclude(attestation__statut='annulee')
    elif statut == 'annulee':
        demandes = demandes.filter(statut='acceptée', attestation__statut='annulee')
    elif statut:
        demandes = demandes.filter(statut=statut)
    if recherche:
        demandes = demandes.filter(utilisateur__nom__icontains=recherche)
    demandes = demandes.order_by('-date_soumission')
    return render(request, 'liste.html', {
        'demandes': demandes,
        'user': request.user,
        'role': role,
        'statut_actif': statut,
        'recherche': recherche,
        'demandes_count': demandes.count(),
    })


# ✅ ACCEPTER
def accepter_demande(request, id):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        if u.role not in ['agent', 'admin']:
            render(request, '403.html', status=403)
    except:
        return redirect('/login/')
    try:
        d = Demande.objects.get(id=id)
        d.statut = "acceptée"
        d.save()
        journaliser(u, 'validation', f"Demande #{id} de {d.utilisateur.nom} validée")

        # Email étudiant — attestation en pièce jointe
        try:
            # Créer/récupérer l'attestation et générer le QR code
            attestation, att_created = Attestation.objects.get_or_create(demande=d)
            if att_created or not attestation.qr_code:
                from .utils import generer_qr_code
                base_url = request.build_absolute_uri('/')[:-1]
                qr_path = generer_qr_code(str(attestation.numero), base_url)
                attestation.qr_code = qr_path
                attestation.save()

            # Appel direct au générateur PDF (sans passer par generer_attestation_pdf
            # qui renverrait un redirect si un check auth échoue → pdf_bytes vide)
            type_doc = d.type_document
            if type_doc == "Attestation de scolarité":
                pdf_resp = generer_pdf_scolarite(request, d, attestation)
            elif type_doc == "Attestation d'inscription":
                pdf_resp = generer_pdf_inscription(request, d, attestation)
            elif type_doc == "Attestation de réussite":
                pdf_resp = generer_pdf_reussite(request, d, attestation)
            elif type_doc == "Attestation de diplôme":
                pdf_resp = generer_pdf_diplome(request, d, attestation)
            else:
                pdf_resp = generer_pdf_scolarite(request, d, attestation)

            pdf_bytes = pdf_resp.content
            if not pdf_bytes:
                raise ValueError("PDF généré vide")

            try:
                etudiant_obj = EtudiantDB.objects.get(matricule=d.matricule)
                email_dest = getattr(etudiant_obj, 'email', None) or d.utilisateur.email
            except EtudiantDB.DoesNotExist:
                email_dest = d.utilisateur.email

            if email_dest:
                msg = EmailMessage(
                    subject="Votre attestation est prête ✅",
                    body=(
                        f"Bonjour {d.utilisateur.nom},\n\n"
                        f"Votre {d.type_document} a été acceptée.\n"
                        f"Veuillez trouver votre attestation en pièce jointe.\n\n"
                        f"Cordialement,\nAttestaFlow EMSI"
                    ),
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[email_dest],
                )
                msg.attach('attestation.pdf', pdf_bytes, 'application/pdf')
                msg.send()
        except Exception:
            pass

        return redirect('/liste/')
    except:
        return HttpResponse("Erreur")



# 🆕 REGISTER
def register(request):
    if request.method == "POST":
        username = request.POST.get('username', '').strip()
        prenom   = request.POST.get('prenom', '').strip()
        password = request.POST.get('password', '')
        password2= request.POST.get('password2', '')
        email    = request.POST.get('email', '').strip()
        matricule= request.POST.get('matricule', '').strip()

        def err(msg):
            return render(request, 'register.html', {
                'error': msg,
                'submitted_matricule': matricule,
            })

        if not matricule:
            return err("Veuillez entrer votre matricule et cliquer sur Vérifier.")

        try:
            etudiant = EtudiantDB.objects.get(matricule=matricule)
        except EtudiantDB.DoesNotExist:
            return err("Matricule introuvable ❌ — vérifiez votre matricule.")

        if Utilisateur.objects.filter(matricule=matricule).exists():
            return err("Ce matricule est déjà associé à un compte existant.")

        if password != password2:
            return err("Les deux mots de passe ne correspondent pas.")

        if len(password) < 6:
            return err("Le mot de passe doit contenir au moins 6 caractères.")

        if User.objects.filter(username=username).exists():
            return err("Ce nom d'utilisateur existe déjà.")

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=etudiant.prenom
        )
        user.save()

        u_obj = Utilisateur.objects.create(
            user=user,
            nom=f"{etudiant.prenom} {etudiant.nom}",
            email=email,
            mot_de_passe='',
            role="beneficiaire",
            matricule=matricule,
        )
        journaliser(u_obj, 'register', f"Nouveau compte créé : {username} (matricule: {matricule})")

        return redirect('/login/')

    return render(request, 'register.html')


# 📄 GENERER ATTESTATION PDF
# ── HELPER commun
# ══════════════════════════════════════════════
# ══════════════════════════════════════════════
# HELPERS COMMUNS — VERSION FINALE CORRIGÉE
# ══════════════════════════════════════════════
def _get_attestation_base(request, demande_id):
    try:
        demande = Demande.objects.get(id=demande_id, statut='acceptée')
    except Demande.DoesNotExist:
        return None, None, None
    attestation, created = Attestation.objects.get_or_create(demande=demande)
    if created or not attestation.qr_code:
        from .utils import generer_qr_code
        base_url = request.build_absolute_uri('/')[:-1]
        qr_path = generer_qr_code(str(attestation.numero), base_url)
        attestation.qr_code = qr_path
        attestation.save()
    journaliser(demande.utilisateur, 'generation_pdf', f"PDF généré pour {demande.utilisateur.nom}")
    return demande, attestation, None


def _draw_page_border(c, W, H):
    from reportlab.lib import colors
    c.setStrokeColor(colors.HexColor('#1a5c2a'))
    c.setLineWidth(3)
    c.rect(15, 15, W - 30, H - 30, fill=0, stroke=1)
    c.setStrokeColor(colors.HexColor('#4a7c59'))
    c.setLineWidth(0.8)
    c.rect(20, 20, W - 40, H - 40, fill=0, stroke=1)


def _draw_header(c, W, H, logo_path, date_str):
    from reportlab.lib import colors
    from reportlab.lib.utils import ImageReader
    from PIL import Image as PILImage
    import io, os

    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    _draw_page_border(c, W, H)

    # Logo EMSI — grande taille
    if os.path.exists(logo_path):
        try:
            pil_img = PILImage.open(logo_path).convert('RGBA')
            bg = PILImage.new('RGB', pil_img.size, (255, 255, 255))
            if pil_img.mode == 'RGBA':
                bg.paste(pil_img, mask=pil_img.split()[3])
            else:
                bg.paste(pil_img)
            img_buf = io.BytesIO()
            bg.save(img_buf, format='PNG')
            img_buf.seek(0)
            c.drawImage(ImageReader(img_buf), 28, H - 108,
                        width=230, height=82,
                        preserveAspectRatio=True, mask='auto')
        except:
            c.setFillColor(colors.HexColor('#1a5c2a'))
            c.setFont("Helvetica-Bold", 22)
            c.drawString(30, H - 70, "EMSI")

    # Date et référence à droite — bien espacés
    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#444444'))
    c.drawRightString(W - 28, H - 38, f"Rabat, le {date_str}")
    c.drawRightString(W - 28, H - 52, "N° Réf : EMSI/DP/2026")

    # Ligne séparatrice verte
    c.setStrokeColor(colors.HexColor('#1a5c2a'))
    c.setLineWidth(2)
    c.line(28, H - 118, W - 28, H - 118)


def _draw_title_banner(c, W, H, title, subtitle=""):
    from reportlab.lib import colors
    # Bandeau principal vert
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.roundRect(28, H - 160, W - 56, 36, 4, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 15)
    c.drawCentredString(W / 2, H - 147, title.upper())
    # Sous-titre
    if subtitle:
        c.setFillColor(colors.HexColor('#e8f5ec'))
        c.roundRect(28, H - 176, W - 56, 15, 4, fill=1, stroke=0)
        c.setFillColor(colors.HexColor('#2d4f38'))
        c.setFont("Helvetica-Bold", 9)
        c.drawCentredString(W / 2, H - 168, subtitle)


def _draw_student_box(c, W, y_top, nom, cin, date_naiss, lieu_naiss, matricule):
    from reportlab.lib import colors
    box_h = 112

    # Fond et bordure
    c.setFillColor(colors.HexColor('#f4faf6'))
    c.setStrokeColor(colors.HexColor('#a8cbb4'))
    c.setLineWidth(1)
    c.roundRect(28, y_top - box_h, W - 56, box_h, 6, fill=1, stroke=1)

    # Header vert
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.roundRect(28, y_top - 22, W - 56, 22, 6, fill=1, stroke=0)
    c.rect(28, y_top - 22, W - 56, 11, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(42, y_top - 14, "▌  INFORMATIONS DE L'ÉTUDIANT(E)")

    # Ligne 1 : Nom + CIN
    y = y_top - 36
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(38, y, "Nom complet :")
    c.drawString(W/2 + 10, y, "CIN :")
    y -= 13
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor('#0f0f0f'))
    c.drawString(38, y, nom.upper())
    c.drawString(W/2 + 10, y, cin.upper())

    # Séparateur
    y -= 8
    c.setStrokeColor(colors.HexColor('#c8e0d0'))
    c.setLineWidth(0.5)
    c.line(34, y, W - 34, y)

    # Ligne 2 : Date + Lieu naissance
    y -= 12
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(38, y, "Date de naissance :")
    c.drawString(W/2 + 10, y, "Lieu de naissance :")
    y -= 13
    c.setFont("Helvetica", 10)
    c.setFillColor(colors.HexColor('#0f0f0f'))
    c.drawString(38, y, date_naiss)
    c.drawString(W/2 + 10, y, lieu_naiss)

    # Séparateur
    y -= 8
    c.setStrokeColor(colors.HexColor('#c8e0d0'))
    c.line(34, y, W - 34, y)

    # Ligne 3 : Matricule — label + valeur sur même ligne, police petite
    y -= 12
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(38, y, "Matricule :")
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.drawString(105, y, matricule)

    return y_top - box_h - 26

def _draw_academic_box(c, W, y_top, filiere, niveau, annee):
    from reportlab.lib import colors
    box_h = 68

    c.setFillColor(colors.HexColor('#f4faf6'))
    c.setStrokeColor(colors.HexColor('#a8cbb4'))
    c.setLineWidth(1)
    c.roundRect(28, y_top - box_h, W - 56, box_h, 5, fill=1, stroke=1)

    # Filière + Niveau
    y = y_top - 16
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(38, y, "Filière :")
    c.drawString(W/2 + 10, y, "Niveau :")
    y -= 14
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.drawString(38, y, filiere)
    c.drawString(W/2 + 10, y, niveau)

    # Séparateur
    y -= 10
    c.setStrokeColor(colors.HexColor('#c8e0d0'))
    c.setLineWidth(0.5)
    c.line(34, y, W - 34, y)

    # Année
    y -= 14
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(38, y, "Année universitaire :")
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.drawString(172, y, annee)

    return y_top - box_h - 14


def _draw_signature_zone(c, W, sig_y):
    from reportlab.lib import colors

    cx = W - 125

    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawCentredString(cx, sig_y, "Le Directeur Pédagogique")
    c.drawCentredString(cx, sig_y - 13, "de l'École Marocaine des Sciences")
    c.drawCentredString(cx, sig_y - 26, "de l'Ingénieur - Rabat")

    c.setStrokeColor(colors.HexColor('#aaaaaa'))
    c.setLineWidth(0.8)
    c.line(cx - 72, sig_y - 32, cx + 72, sig_y - 32)

    # Signature manuscrite
    c.saveState()
    c.translate(cx - 60, sig_y - 78)
    c.setStrokeColor(colors.HexColor('#1a1a1a'))
    c.setLineWidth(1.2)
    p = c.beginPath()
    p.moveTo(10,30); p.curveTo(15,45,25,48,30,40)
    p.curveTo(35,32,30,20,20,18); p.curveTo(10,16,5,25,10,30)
    c.drawPath(p, stroke=1, fill=0)
    p2 = c.beginPath()
    p2.moveTo(28,35); p2.curveTo(40,42,50,38,60,32)
    p2.curveTo(70,26,75,20,85,22); p2.curveTo(95,24,100,30,110,28)
    p2.curveTo(118,26,122,18,130,20)
    c.drawPath(p2, stroke=1, fill=0)
    p3 = c.beginPath()
    p3.moveTo(25,15); p3.curveTo(50,8,80,5,120,10)
    p3.curveTo(135,12,140,8,145,3)
    c.drawPath(p3, stroke=1, fill=0)
    c.restoreState()

    # Cachet remonté
    c.setStrokeColor(colors.HexColor('#1a5c2a'))
    c.setFillColor(colors.HexColor('#f0fdf4'))
    c.setLineWidth(2)
    c.circle(cx, sig_y - 115, 50, fill=1, stroke=1)
    c.setStrokeColor(colors.HexColor('#4a7c59'))
    c.setLineWidth(0.5)
    c.circle(cx, sig_y - 115, 45, fill=0, stroke=1)

    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.setFont("Helvetica-Bold", 6.2)
    c.drawCentredString(cx, sig_y - 99, "ÉCOLE MAROCAINE DES")
    c.drawCentredString(cx, sig_y - 109, "SCIENCES DE L'INGÉNIEUR")
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(cx, sig_y - 119, "RABAT")
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(cx, sig_y - 131, "Ecole Reconnue par l'Etat")
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(cx, sig_y - 143, "✦  ✦  ✦")

    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor('#555555'))
    c.drawCentredString(cx, sig_y - 157, "Signature & Cachet Officiel")


def _draw_footer_qr(c, W, attestation, date_str):
    from reportlab.lib import colors
    import os
    from django.conf import settings

    # Ligne séparatrice
    c.setStrokeColor(colors.HexColor('#1a5c2a'))
    c.setLineWidth(1)
    c.line(28, 168, W - 28, 168)

    # Zone QR
    c.setFillColor(colors.HexColor('#f4faf6'))
    c.setStrokeColor(colors.HexColor('#a8cbb4'))
    c.setLineWidth(1)
    c.roundRect(28, 34, W - 56, 130, 5, fill=1, stroke=1)

    # QR code
    qr_abs = os.path.join(settings.MEDIA_ROOT, str(attestation.qr_code))
    if os.path.exists(qr_abs):
        c.drawImage(qr_abs, 40, 44, width=105, height=105)

    # Texte vérification
    tx = 158
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.setFont("Helvetica-Bold", 9)
    c.drawString(tx, 154, "VÉRIFICATION D'AUTHENTICITÉ")

    c.setStrokeColor(colors.HexColor('#c8e0d0'))
    c.setLineWidth(0.5)
    c.line(tx, 150, W - 36, 150)

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor('#444444'))
    c.drawString(tx, 136, "Scannez le QR code pour vérifier l'authenticité")
    c.drawString(tx, 124, "de ce document sur notre plateforme en ligne.")

    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#1a5c2a'))
    num = str(attestation.numero).upper()
    c.drawString(tx, 108, f"N° : {num}")

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(tx, 94, f"Date d'émission : {date_str}")
    c.drawString(tx, 80, "Document officiel — EMSI Rabat")
    c.drawString(tx, 66, "Toute falsification expose à des poursuites.")

    # Footer bas
    c.setStrokeColor(colors.HexColor('#1a5c2a'))
    c.setLineWidth(1)
    c.line(28, 28, W - 28, 28)
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.setFont("Helvetica-Bold", 7.5)
    c.drawCentredString(W/2, 19, "Ecole Marocaine des Sciences de l'Ingénieur  —  Ecole Reconnue par l'Etat")
    c.setFillColor(colors.HexColor('#777777'))
    c.setFont("Helvetica", 7)
    c.drawCentredString(W/2, 9, "49 Rue Patrice Lumumba, Rabat  |  0537 76 40 50  |  www.emsi.ma  |  RC: 47785")


# ══════════════════════════════════════════════
# 1️⃣ ATTESTATION DE SCOLARITÉ
# ══════════════════════════════════════════════
def generer_pdf_scolarite(request, demande, attestation):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    import io, os
    from datetime import date
    from django.conf import settings

    try:
        etudiant    = EtudiantDB.objects.get(matricule=demande.matricule)
        nom         = f"{etudiant.prenom} {etudiant.nom}"
        cin         = etudiant.cin or "—"
        date_naiss  = etudiant.date_naissance or "—"
        lieu_naiss  = etudiant.lieu_naissance or "—"
        filiere     = etudiant.filiere or "—"
        niveau      = etudiant.niveau or "—"
        annee       = etudiant.annee_universitaire or "—"
        matricule   = etudiant.matricule
        annee_debut = etudiant.annee_debut or "—"
        annee_fin   = etudiant.annee_fin or "—"
        nationalite = etudiant.nationalite or "Marocaine"
    except EtudiantDB.DoesNotExist:
        nom         = demande.utilisateur.nom
        cin         = demande.cin or "—"
        date_naiss  = demande.date_naissance or "—"
        lieu_naiss  = demande.lieu_naissance or "—"
        filiere     = demande.filiere or "—"
        niveau      = demande.niveau or "—"
        annee       = demande.annee_universitaire or "—"
        matricule   = demande.matricule or "—"
        annee_debut = annee_fin = nationalite = "—"
    date_str   = attestation.date_emission.strftime('%d/%m/%Y') if attestation.date_emission else date.today().strftime('%d/%m/%Y')
    logo_path  = os.path.join(settings.BASE_DIR, 'gestion', 'static', 'images', 'emsi_logo.png')

    buffer = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    _draw_header(c, W, H, logo_path, date_str)
    _draw_title_banner(c, W, H, "Attestation de Scolarité", "Année Universitaire " + annee)

    # Intro — commence à y fixe sous le titre
    y = H - 194
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y, "Je soussigné, le Directeur Pédagogique de l'École Marocaine des Sciences de")
    c.drawString(32, y - 15, "L'Ingénieur — Rabat, atteste par la présente que l'étudiant(e) :")

    # Box étudiant — Y fixe
    y_after_student = _draw_student_box(c, W, y - 32, nom, cin, date_naiss, lieu_naiss, matricule)

    # Texte
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y_after_student, "Est régulièrement inscrit(e) et suit les cours dans notre établissement :")

    # Box académique
    y_after_acad = _draw_academic_box(c, W, y_after_student - 16, filiere, niveau, annee)

    # Phrase finale — pleine largeur, bien séparée
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y_after_acad, "Cette attestation est délivrée à l'intéressé(e) pour servir et valoir ce que de droit.")

    # Signature — positionnée à gauche de la phrase finale mais plus bas
    _draw_signature_zone(c, W, y_after_acad - 50)
    _draw_footer_qr(c, W, attestation, date_str)

    c.save()
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="scolarite_{nom}.pdf"'
    return response


# ══════════════════════════════════════════════
# 2️⃣ ATTESTATION DE RÉUSSITE
# ══════════════════════════════════════════════
def generer_pdf_reussite(request, demande, attestation):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    import io, os
    from datetime import date
    from django.conf import settings

    try:
        etudiant    = EtudiantDB.objects.get(matricule=demande.matricule)
        nom         = f"{etudiant.prenom} {etudiant.nom}"
        cin         = etudiant.cin or "—"
        date_naiss  = etudiant.date_naissance or "—"
        lieu_naiss  = etudiant.lieu_naissance or "—"
        filiere     = etudiant.filiere or "—"
        niveau      = etudiant.niveau or "—"
        annee       = etudiant.annee_universitaire or "—"
        matricule   = etudiant.matricule
        annee_debut = etudiant.annee_debut or "—"
        annee_fin   = etudiant.annee_fin or "—"
        nationalite = etudiant.nationalite or "Marocaine"
    except EtudiantDB.DoesNotExist:
        nom         = demande.utilisateur.nom
        cin         = demande.cin or "—"
        date_naiss  = demande.date_naissance or "—"
        lieu_naiss  = demande.lieu_naissance or "—"
        filiere     = demande.filiere or "—"
        niveau      = demande.niveau or "—"
        annee       = demande.annee_universitaire or "—"
        matricule   = demande.matricule or "—"
        annee_debut = annee_fin = nationalite = "—"
    date_str   = attestation.date_emission.strftime('%d/%m/%Y') if attestation.date_emission else date.today().strftime('%d/%m/%Y')
    logo_path  = os.path.join(settings.BASE_DIR, 'gestion', 'static', 'images', 'emsi_logo.png')

    buffer = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    _draw_header(c, W, H, logo_path, date_str)
    _draw_title_banner(c, W, H, "Attestation de Réussite", "Année Universitaire " + annee)

    y = H - 194
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y, "Je soussigné, le Directeur Pédagogique de l'École Marocaine des Sciences de")
    c.drawString(32, y - 15, "L'Ingénieur — Rabat, atteste par la présente que l'étudiant(e) :")

    y_after_student = _draw_student_box(c, W, y - 32, nom, cin, date_naiss, lieu_naiss, matricule)

    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y_after_student, "A satisfait aux épreuves et examens de fin d'année :")

    y_after_acad = _draw_academic_box(c, W, y_after_student - 16, filiere, niveau, annee)

    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y_after_acad, "En conséquence, l'intéressé(e) est déclaré(e) :")

    # Badge ADMIS — plus petit
    badge_y = y_after_acad - 14
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.roundRect(W/2 - 70, badge_y - 22, 140, 28, 6, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(W/2, badge_y - 8, "✓   ADMIS(E)   ✓")

    # Phrase finale
    phrase_y = badge_y - 40
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, phrase_y, "Cette attestation de réussite est délivrée pour servir et valoir ce que de droit.")

    # Signature remontée
    sig_y = phrase_y + 10
    cx = W - 125

    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawCentredString(cx, sig_y, "Le Directeur Pédagogique")
    c.drawCentredString(cx, sig_y - 13, "de l'École Marocaine des Sciences")
    c.drawCentredString(cx, sig_y - 26, "de l'Ingénieur - Rabat")

    c.setStrokeColor(colors.HexColor('#aaaaaa'))
    c.setLineWidth(0.8)
    c.line(cx - 72, sig_y - 32, cx + 72, sig_y - 32)

    # Signature manuscrite
    c.saveState()
    c.translate(cx - 60, sig_y - 78)
    c.setStrokeColor(colors.HexColor('#1a1a1a'))
    c.setLineWidth(1.2)
    p = c.beginPath()
    p.moveTo(10,30); p.curveTo(15,45,25,48,30,40)
    p.curveTo(35,32,30,20,20,18); p.curveTo(10,16,5,25,10,30)
    c.drawPath(p, stroke=1, fill=0)
    p2 = c.beginPath()
    p2.moveTo(28,35); p2.curveTo(40,42,50,38,60,32)
    p2.curveTo(70,26,75,20,85,22); p2.curveTo(95,24,100,30,110,28)
    p2.curveTo(118,26,122,18,130,20)
    c.drawPath(p2, stroke=1, fill=0)
    p3 = c.beginPath()
    p3.moveTo(25,15); p3.curveTo(50,8,80,5,120,10)
    p3.curveTo(135,12,140,8,145,3)
    c.drawPath(p3, stroke=1, fill=0)
    c.restoreState()

    # Cachet
    c.setStrokeColor(colors.HexColor('#1a5c2a'))
    c.setFillColor(colors.HexColor('#f0fdf4'))
    c.setLineWidth(2)
    c.circle(cx, sig_y - 105, 50, fill=1, stroke=1)
    c.setStrokeColor(colors.HexColor('#4a7c59'))
    c.setLineWidth(0.5)
    c.circle(cx, sig_y - 105, 45, fill=0, stroke=1)

    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.setFont("Helvetica-Bold", 6.2)
    c.drawCentredString(cx, sig_y - 89, "ÉCOLE MAROCAINE DES")
    c.drawCentredString(cx, sig_y - 99, "SCIENCES DE L'INGÉNIEUR")
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(cx, sig_y - 109, "RABAT")
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(cx, sig_y - 121, "Ecole Reconnue par l'Etat")
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(cx, sig_y - 133, "✦  ✦  ✦")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor('#555555'))
    c.drawCentredString(cx, sig_y - 147, "Signature & Cachet Officiel")

    _draw_footer_qr(c, W, attestation, date_str)

    c.save()
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="reussite_{nom}.pdf"'
    return response


# ══════════════════════════════════════════════
# 3️⃣ ATTESTATION D'INSCRIPTION
# ══════════════════════════════════════════════
def generer_pdf_inscription(request, demande, attestation):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    import io, os
    from datetime import date
    from django.conf import settings

    try:
        etudiant    = EtudiantDB.objects.get(matricule=demande.matricule)
        nom         = f"{etudiant.prenom} {etudiant.nom}"
        cin         = etudiant.cin or "—"
        date_naiss  = etudiant.date_naissance or "—"
        lieu_naiss  = etudiant.lieu_naissance or "—"
        filiere     = etudiant.filiere or "—"
        niveau      = etudiant.niveau or "—"
        annee       = etudiant.annee_universitaire or "—"
        matricule   = etudiant.matricule
        annee_debut = etudiant.annee_debut or "—"
        annee_fin   = etudiant.annee_fin or "—"
        nationalite = etudiant.nationalite or "Marocaine"
    except EtudiantDB.DoesNotExist:
        nom         = demande.utilisateur.nom
        cin         = demande.cin or "—"
        date_naiss  = demande.date_naissance or "—"
        lieu_naiss  = demande.lieu_naissance or "—"
        filiere     = demande.filiere or "—"
        niveau      = demande.niveau or "—"
        annee       = demande.annee_universitaire or "—"
        matricule   = demande.matricule or "—"
        annee_debut = annee_fin = nationalite = "—"
    date_str   = attestation.date_emission.strftime('%d/%m/%Y') if attestation.date_emission else date.today().strftime('%d/%m/%Y')
    logo_path  = os.path.join(settings.BASE_DIR, 'gestion', 'static', 'images', 'emsi_logo.png')

    buffer = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    _draw_header(c, W, H, logo_path, date_str)
    _draw_title_banner(c, W, H, "Attestation d'Inscription", "Année Universitaire " + annee)

    y = H - 194
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y, "Je soussigné, le Directeur Pédagogique de l'École Marocaine des Sciences de")
    c.drawString(32, y - 15, "L'Ingénieur — Rabat, certifie que l'étudiant(e) :")

    y_after_student = _draw_student_box(c, W, y - 32, nom, cin, date_naiss, lieu_naiss, matricule)

    # Texte inscription
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y_after_student, "Est dûment inscrit(e) dans notre établissement pour l'année universitaire :")

    # Badge année — petit et inline
    badge_y = y_after_student - 16
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.roundRect(32, badge_y - 22, 140, 26, 5, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(46, badge_y - 7, annee)

    # Texte conditions
    y_cond = badge_y - 38
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y_cond, "Dans les conditions académiques suivantes :")

    # Box académique inscription
    box_top = y_cond - 16
    box_h = 76
    c.setFillColor(colors.HexColor('#f4faf6'))
    c.setStrokeColor(colors.HexColor('#a8cbb4'))
    c.setLineWidth(1)
    c.roundRect(28, box_top - box_h, W - 56, box_h, 5, fill=1, stroke=1)

    # Filière
    yb = box_top - 14
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(38, yb, "Filière d'études :")
    yb -= 13
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.drawString(38, yb, filiere)

    # Séparateur
    yb -= 9
    c.setStrokeColor(colors.HexColor('#c8e0d0'))
    c.setLineWidth(0.5)
    c.line(34, yb, W - 34, yb)

    # Niveau + Matricule sur même ligne
    yb -= 12
    c.setFont("Helvetica-Bold", 8)
    c.setFillColor(colors.HexColor('#666666'))
    c.drawString(38, yb, "Niveau :")
    c.drawString(W/2 + 10, yb, "Matricule :")
    yb -= 13
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.drawString(38, yb, niveau)
    c.drawString(W/2 + 10, yb, matricule)

    # Phrase finale — bien espacée
    phrase_y = box_top - box_h - 18
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, phrase_y, "Cette attestation d'inscription est délivrée pour servir et valoir ce que de droit.")

    # Signature remontée
    sig_y = phrase_y + 10
    cx = W - 125

    c.setFont("Helvetica", 9)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawCentredString(cx, sig_y, "Le Directeur Pédagogique")
    c.drawCentredString(cx, sig_y - 13, "de l'École Marocaine des Sciences")
    c.drawCentredString(cx, sig_y - 26, "de l'Ingénieur - Rabat")

    c.setStrokeColor(colors.HexColor('#aaaaaa'))
    c.setLineWidth(0.8)
    c.line(cx - 72, sig_y - 32, cx + 72, sig_y - 32)

    # Signature manuscrite
    c.saveState()
    c.translate(cx - 60, sig_y - 78)
    c.setStrokeColor(colors.HexColor('#1a1a1a'))
    c.setLineWidth(1.2)
    p = c.beginPath()
    p.moveTo(10,30); p.curveTo(15,45,25,48,30,40)
    p.curveTo(35,32,30,20,20,18); p.curveTo(10,16,5,25,10,30)
    c.drawPath(p, stroke=1, fill=0)
    p2 = c.beginPath()
    p2.moveTo(28,35); p2.curveTo(40,42,50,38,60,32)
    p2.curveTo(70,26,75,20,85,22); p2.curveTo(95,24,100,30,110,28)
    p2.curveTo(118,26,122,18,130,20)
    c.drawPath(p2, stroke=1, fill=0)
    p3 = c.beginPath()
    p3.moveTo(25,15); p3.curveTo(50,8,80,5,120,10)
    p3.curveTo(135,12,140,8,145,3)
    c.drawPath(p3, stroke=1, fill=0)
    c.restoreState()

    # Cachet
    c.setStrokeColor(colors.HexColor('#1a5c2a'))
    c.setFillColor(colors.HexColor('#f0fdf4'))
    c.setLineWidth(2)
    c.circle(cx, sig_y - 105, 50, fill=1, stroke=1)
    c.setStrokeColor(colors.HexColor('#4a7c59'))
    c.setLineWidth(0.5)
    c.circle(cx, sig_y - 105, 45, fill=0, stroke=1)

    c.setFillColor(colors.HexColor('#1a5c2a'))
    c.setFont("Helvetica-Bold", 6.2)
    c.drawCentredString(cx, sig_y - 89, "ÉCOLE MAROCAINE DES")
    c.drawCentredString(cx, sig_y - 99, "SCIENCES DE L'INGÉNIEUR")
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(cx, sig_y - 109, "RABAT")
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(cx, sig_y - 121, "Ecole Reconnue par l'Etat")
    c.setFont("Helvetica-Bold", 8)
    c.drawCentredString(cx, sig_y - 133, "✦  ✦  ✦")
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor('#555555'))
    c.drawCentredString(cx, sig_y - 147, "Signature & Cachet Officiel")

    _draw_footer_qr(c, W, attestation, date_str)

    c.save()
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="inscription_{nom}.pdf"'
    return response


# ══════════════════════════════════════════════
# 4️⃣ ATTESTATION DE DIPLÔME
# ══════════════════════════════════════════════
def generer_pdf_diplome(request, demande, attestation):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    import io, os
    from datetime import date
    from django.conf import settings

    try:
        etudiant    = EtudiantDB.objects.get(matricule=demande.matricule)
        nom         = f"{etudiant.prenom} {etudiant.nom}"
        cin         = etudiant.cin or "—"
        date_naiss  = etudiant.date_naissance or "—"
        lieu_naiss  = etudiant.lieu_naissance or "—"
        filiere     = etudiant.filiere or "—"
        niveau      = etudiant.niveau or "—"
        annee       = etudiant.annee_universitaire or "—"
        matricule   = etudiant.matricule
        annee_debut = etudiant.annee_debut or "—"
        annee_fin   = etudiant.annee_fin or "—"
        nationalite = etudiant.nationalite or "Marocaine"
    except EtudiantDB.DoesNotExist:
        nom         = demande.utilisateur.nom
        cin         = demande.cin or "—"
        date_naiss  = demande.date_naissance or "—"
        lieu_naiss  = demande.lieu_naissance or "—"
        filiere     = demande.filiere or "—"
        niveau      = demande.niveau or "—"
        annee       = demande.annee_universitaire or "—"
        matricule   = demande.matricule or "—"
        annee_debut = annee_fin = nationalite = "—"
    date_str  = attestation.date_emission.strftime('%d/%m/%Y') if attestation.date_emission else date.today().strftime('%d/%m/%Y')
    logo_path = os.path.join(settings.BASE_DIR, 'gestion', 'static', 'images', 'emsi_logo.png')

    buffer = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buffer, pagesize=A4)

    _draw_header(c, W, H, logo_path, date_str)
    _draw_title_banner(c, W, H, "Attestation de Diplôme", "Année Universitaire " + annee)

    y = H - 200
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y,      "Le Directeur Pédagogique de l'École Marocaine des Sciences de l'Ingénieur")
    c.drawString(32, y - 15, "(EMSI) — Rabat,")

    y -= 36
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(32, y, "Vu le procès-verbal de délibération des résultats,")

    y -= 26
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y, "Atteste que le nommé(e) :")

    y -= 20
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(colors.HexColor('#0f0f0f'))
    c.drawString(48, y, nom.upper())

    y -= 20
    c.setFont("Helvetica", 10.5)
    c.setFillColor(colors.HexColor('#333333'))
    c.drawString(32, y,      f"né(e) le {date_naiss} à {lieu_naiss}, de nationalité {nationalite},")
    c.drawString(32, y - 16, f"inscrit(e) sous le numéro matricule {matricule}")
    c.drawString(32, y - 32, f"dans la Spécialité {filiere} de cette École,")
    c.drawString(32, y - 48, f"a satisfait aux exigences du programme d'études de la {niveau}")
    c.drawString(32, y - 64, f"de {annee_debut} à {annee_fin}.")

    y -= 88
    c.drawString(32, y,      "En foi de quoi, la présente attestation de diplôme lui est délivrée pour")
    c.drawString(32, y - 16, "qu'il/elle en jouisse avec les droits et prérogatives qui y sont attachés.")

    _draw_signature_zone(c, W, y - 50)
    _draw_footer_qr(c, W, attestation, date_str)

    c.save()
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="diplome_{nom}.pdf"'
    return response


# ══════════════════════════════════════════════
# ROUTEUR PRINCIPAL
# ══════════════════════════════════════════════
def generer_attestation_pdf(request, demande_id):
    if not request.user.is_authenticated:
        return redirect('/login/')
    demande, attestation, _ = _get_attestation_base(request, demande_id)
    if not demande:
        return HttpResponse("Demande introuvable ou non acceptée.", status=404)
    type_doc = demande.type_document
    if type_doc == "Attestation de scolarité":
        return generer_pdf_scolarite(request, demande, attestation)
    elif type_doc == "Attestation d'inscription":
        return generer_pdf_inscription(request, demande, attestation)
    elif type_doc == "Attestation de réussite":
        return generer_pdf_reussite(request, demande, attestation)
    elif type_doc == "Attestation de diplôme":
        return generer_pdf_diplome(request, demande, attestation)
    else:
        return generer_pdf_scolarite(request, demande, attestation)

# 🔍 VERIFIER ATTESTATION QR
def verifier_attestation(request, numero):
    try:
        attestation = Attestation.objects.get(numero=numero)
        u = attestation.demande.utilisateur
        d = attestation.demande

        # Récupérer le rôle de l'utilisateur connecté
        role = 'beneficiaire'
        demandes_count = 0
        if request.user.is_authenticated:
            try:
                u_connecte = Utilisateur.objects.get(user=request.user)
                role = u_connecte.role
                demandes_count = Demande.objects.filter(utilisateur=u_connecte).count()
            except:
                pass

        return render(request, 'verifier.html', {
            'valide': attestation.statut == 'valide',
            'annulee': attestation.statut == 'annulee',
            'nom': u.nom,
            'filiere': d.filiere or '—',
            'niveau': d.niveau or '—',
            'annee': d.annee_universitaire or '—',
            'date_emission': attestation.date_emission,
            'numero': attestation.numero,
            'user': request.user,
            'role': role,
            'demandes_count': demandes_count,
        })
    except Attestation.DoesNotExist:
        role = 'beneficiaire'
        demandes_count = 0
        if request.user.is_authenticated:
            try:
                u_connecte = Utilisateur.objects.get(user=request.user)
                role = u_connecte.role
                demandes_count = Demande.objects.filter(utilisateur=u_connecte).count()
            except:
                pass
        return render(request, 'verifier.html', {
            'valide': False,
            'annulee': False,
            'user': request.user,
            'role': role,
            'demandes_count': demandes_count,
        })


# 📋 JOURNAL
def journal_actions(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        if u.role not in ['agent', 'admin']:
            render(request, '403.html', status=403)
    except:
        return redirect('/login/')
    actions = JournalAction.objects.all().order_by('-date_action')[:100]
    return render(request, 'journal.html', {
        'actions': actions,
        'user': request.user,
        'role': u.role,
        'demandes_count': Demande.objects.count(),
    })


# 🚫 ANNULER ATTESTATION
def annuler_attestation(request, demande_id):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        if u.role not in ['agent', 'admin']:
            render(request, '403.html', status=403)
    except:
        return redirect('/login/')
    try:
        attestation = Attestation.objects.get(demande__id=demande_id)
        attestation.statut = 'annulee'
        attestation.save()
        journaliser(u, 'validation', f"Attestation de la demande #{demande_id} annulée")
    except Attestation.DoesNotExist:
        pass
    return redirect('/liste/')


# ── ADMIN ──
def check_admin(request):
    if not request.user.is_authenticated:
        return None
    try:
        u = Utilisateur.objects.get(user=request.user)
        if u.role != 'admin':
            return None
        return u
    except:
        return None


# 📊 ADMIN STATS — agent et admin autorisés
def admin_stats(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        if u.role not in ['agent', 'admin']:
            return redirect('/dashboard/')
    except:
        return redirect('/login/')
    from datetime import date as _date
    demandes = Demande.objects.all()
    total = demandes.count() or 1
    approuvees = demandes.filter(statut='acceptée').count()
    refusees = demandes.filter(statut='refusée').count()
    en_attente = demandes.filter(statut='en attente').count()
    attestations = Attestation.objects.count()
    taux = round((approuvees / total) * 100) if total else 0
    pct_attente = round((en_attente / total) * 100) if total else 0
    pct_refus = round((refusees / total) * 100) if total else 0

    # Répartition par les 4 vrais types
    sc  = demandes.filter(type_document__icontains='scolarité').count()
    ins = demandes.filter(type_document__icontains='inscription').count()
    reu = demandes.filter(type_document__icontains='réussite').count()
    dip = demandes.filter(type_document__icontains='diplôme').count()
    pct_sc  = round((sc  / total) * 100) if total else 0
    pct_ins = round((ins / total) * 100) if total else 0
    pct_reu = round((reu / total) * 100) if total else 0
    pct_dip = round((dip / total) * 100) if total else 0

    # Demandes par jour — 7 derniers jours glissants
    from datetime import timedelta
    today = _date.today()
    daily_data = []
    daily_labels = []
    for i in range(6, -1, -1):
        d_day = today - timedelta(days=i)
        cnt = Demande.objects.filter(
            date_soumission__year=d_day.year,
            date_soumission__month=d_day.month,
            date_soumission__day=d_day.day,
        ).count()
        daily_data.append(cnt)
        daily_labels.append(f"{d_day.day:02d}/{d_day.month:02d}")

    actions = JournalAction.objects.all().order_by('-date_action')[:8]
    return render(request, 'admin_stats.html', {
        'user': request.user, 'role': u.role,
        'total_demandes': total, 'approuvees': approuvees,
        'refusees': refusees, 'en_attente': en_attente,
        'attestations_generees': attestations,
        'taux_validation': taux, 'pct_attente': pct_attente,
        'pct_refus': pct_refus,
        'pct_scolarite': pct_sc,  'cnt_scolarite': sc,
        'pct_inscription': pct_ins, 'cnt_inscription': ins,
        'pct_reussite': pct_reu,  'cnt_reussite': reu,
        'pct_diplome': pct_dip,   'cnt_diplome': dip,
        'daily_data': json.dumps(daily_data),
        'daily_labels': json.dumps(daily_labels),
        'actions_recentes': actions,
        'demandes_count': Demande.objects.count(),
    })


# 👥 ADMIN USERS
def admin_users(request):
    u = check_admin(request)
    if not u:
        return redirect('/login/')
    utilisateurs = Utilisateur.objects.all().order_by('role', 'nom')
    return render(request, 'admin_users.html', {
        'user': request.user, 'role': u.role,
        'utilisateurs': utilisateurs,
        'total_users': utilisateurs.count(),
        'total_beneficiaires': utilisateurs.filter(role='beneficiaire').count(),
        'total_agents': utilisateurs.filter(role='agent').count(),
        'total_admins': utilisateurs.filter(role='admin').count(),
        'demandes_count': Demande.objects.count(),
    })


# 📋 ADMIN DEMANDES
def admin_demandes(request):
    u = check_admin(request)
    if not u:
        return redirect('/login/')
    demandes = Demande.objects.all().order_by('-date_soumission')
    total = demandes.count()
    return render(request, 'admin_demandes.html', {
        'user': request.user, 'role': u.role,
        'demandes': demandes, 'total_demandes': total,
        'en_attente': demandes.filter(statut='en attente').count(),
        'approuvees': demandes.filter(statut='acceptée').count(),
        'refusees': demandes.filter(statut='refusée').count(),
        'demandes_count': Demande.objects.count(),
    })


# 📜 ADMIN ATTESTATIONS — agent et admin autorisés
def admin_attestations(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        if u.role not in ['agent', 'admin']:
            return redirect('/dashboard/')
    except:
        return redirect('/login/')
    attestations = Attestation.objects.all().order_by('-date_emission')
    return render(request, 'admin_attestations.html', {
        'user': request.user, 'role': u.role,
        'attestations': attestations,
        'total_attestations': attestations.count(),
        'att_valides': attestations.filter(statut='valide').count(),
        'att_annulees': attestations.filter(statut='annulee').count(),
        'att_qr_scans': 0,
        'demandes_count': Demande.objects.count(),
    })


# 🔄 ADMIN CHANGER RÔLE
def admin_change_role(request, user_id):
    u = check_admin(request)
    if not u:
        return JsonResponse({'error': 'Accès refusé'}, status=403)
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            role = data.get('role')
            if role not in ['beneficiaire', 'agent', 'admin']:
                return JsonResponse({'error': 'Rôle invalide'}, status=400)
            utilisateur = Utilisateur.objects.get(id=user_id)
            utilisateur.role = role
            utilisateur.save()
            journaliser(u, 'validation', f"Rôle de {utilisateur.nom} changé en {role}")
            return JsonResponse({'success': True, 'role': role})
        except Utilisateur.DoesNotExist:
            return JsonResponse({'error': 'Utilisateur introuvable'}, status=404)
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Méthode non autorisée'}, status=405)


# 📜 MES ATTESTATIONS
def mes_attestations(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
    except:
        return redirect('/login/')
    attestations = Attestation.objects.filter(
        demande__utilisateur=u
    ).order_by('-date_emission')
    return render(request, 'mes_attestations.html', {
        'user': request.user,
        'role': u.role,
        'attestations': attestations,
        'demandes_count': Demande.objects.filter(utilisateur=u).count(),
    })


def aide(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
    except:
        return redirect('/login/')
    demandes_count = Demande.objects.filter(utilisateur=u).count() if u.role == 'beneficiaire' else Demande.objects.count()
    return render(request, 'aide.html', {
        'user': request.user,
        'role': u.role,
        'demandes_count': demandes_count,
    })


# 👤 PROFIL
def profil(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
    except:
        return redirect('/login/')
    return render(request, 'profil.html', {
        'user': request.user,
        'utilisateur': u,
        'role': u.role,
        'nb_demandes': Demande.objects.filter(utilisateur=u).count(),
        'nb_attestations': Attestation.objects.filter(demande__utilisateur=u).count(),
        'demandes_count': Demande.objects.filter(utilisateur=u).count(),
    })


# 🔍 VERIFIER PAGE
def verifier_page(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
    except:
        return redirect('/login/')

    numero = request.GET.get('numero', '').strip()
    resultat = None

    if numero:
        try:
            attestation = Attestation.objects.get(numero=numero)
            resultat = {
                'trouve': True,
                'valide': attestation.statut == 'valide',
                'annulee': attestation.statut == 'annulee',
                'nom': attestation.demande.utilisateur.nom,
                'type': attestation.demande.type_document,
                'date': attestation.date_emission,
                'numero': attestation.numero,
            }
        except Exception:
            resultat = {'trouve': False}

    return render(request, 'verifier_page.html', {
        'user': request.user,
        'role': u.role,
        'resultat': resultat,
        'numero': numero,
        'demandes_count': Demande.objects.filter(utilisateur=u).count(),
    })


# ❓ AIDE
def aide(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
    except:
        return redirect('/login/')
    return render(request, 'aide.html', {
        'user': request.user,
        'role': u.role,
        'demandes_count': Demande.objects.filter(utilisateur=u).count(),
    })


# ⚙️ PARAMETRES
def parametres(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    try:
        u = Utilisateur.objects.get(user=request.user)
        if u.role != 'admin':
            return redirect('/dashboard/')
    except:
        return redirect('/login/')
    return render(request, 'parametres.html', {
        'user': request.user,
        'role': u.role,
        'demandes_count': Demande.objects.count(),
        'total_users': Utilisateur.objects.count(),
        'total_demandes': Demande.objects.count(),
        'total_attestations': Attestation.objects.count(),
        'total_actions': JournalAction.objects.count(),
        'total_beneficiaires': Utilisateur.objects.filter(role='beneficiaire').count(),
        'total_agents': Utilisateur.objects.filter(role='agent').count(),
        'total_admins': Utilisateur.objects.filter(role='admin').count(),
        'en_attente': Demande.objects.filter(statut='en attente').count(),
        'approuvees': Demande.objects.filter(statut='acceptée').count(),
        'refusees': Demande.objects.filter(statut='refusée').count(),
    })

# 🔑 CHANGER MOT DE PASSE
def changer_password(request):
    if not request.user.is_authenticated:
        return redirect('/login/')
    if request.method == 'POST':
        ancien = request.POST.get('ancien_password')
        nouveau = request.POST.get('nouveau_password')
        confirmer = request.POST.get('confirmer_password')
        user = request.user
        if not user.check_password(ancien):
            return redirect('/profil/?error=ancien')
        if nouveau != confirmer:
            return redirect('/profil/?error=confirmer')
        if len(nouveau) < 6:
            return redirect('/profil/?error=court')
        user.set_password(nouveau)
        user.save()
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, user)
        return redirect('/profil/?success=1')
    return redirect('/profil/')

# 🗑️ SUPPRIMER UTILISATEUR
def supprimer_utilisateur(request, user_id):
    u = check_admin(request)
    if not u:
        return redirect('/login/')
    try:
        utilisateur = Utilisateur.objects.get(id=user_id)
        if utilisateur.user == request.user:
            return redirect('/admin-users/')
        utilisateur.user.delete()
    except Utilisateur.DoesNotExist:
        pass
    return redirect('/admin-users/')


# 🔍 VÉRIFIER MATRICULE (AJAX)
def verifier_matricule(request, matricule):
    try:
        e = EtudiantDB.objects.get(matricule=matricule)
        return JsonResponse({
            'found': True,
            'nom': e.nom,
            'prenom': e.prenom,
            'filiere': e.filiere,
            'niveau': e.niveau,
            'annee_universitaire': e.annee_universitaire,
        })
    except EtudiantDB.DoesNotExist:
        return JsonResponse({'found': False})


# 404
def page_404(request, exception):
    return render(request, '404.html', status=404)


# 403
def page_403(request, exception=None):
    return render(request, '403.html', status=403)


# 🔍 VÉRIFICATION PUBLIQUE QR
def verifier_public(request, numero):
    try:
        attestation = Attestation.objects.get(numero=numero)
        d = attestation.demande
        u = d.utilisateur
        return render(request, 'verifier_public.html', {
            'valide': attestation.statut == 'valide',
            'annulee': attestation.statut == 'annulee',
            'nom': u.nom,
            'type_doc': d.type_document,
            'filiere': d.filiere or '—',
            'niveau': d.niveau or '—',
            'annee': d.annee_universitaire or '—',
            'date_emission': attestation.date_emission,
            'numero': attestation.numero,
        })
    except Attestation.DoesNotExist:
        return render(request, 'verifier_public.html', {
            'valide': False,
            'annulee': False,
        })