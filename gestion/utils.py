import qrcode
import os
from django.conf import settings


def generer_qr_code(numero_attestation, base_url=None):
    NGROK_URL = "https://bluff-riverbank-suffix.ngrok-free.dev"

    if base_url and "127.0.0.1" not in base_url and "localhost" not in base_url:
        url_verification = f"{base_url}/verifier/{numero_attestation}/?ngrok-skip-browser-warning=true"
    else:
        url_verification = f"{NGROK_URL}/verifier/{numero_attestation}/?ngrok-skip-browser-warning=true"

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=8,
        border=3,
    )
    qr.add_data(url_verification)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1a5c2a", back_color="white")

    os.makedirs(os.path.join(settings.MEDIA_ROOT, 'qrcodes'), exist_ok=True)
    path = os.path.join(settings.MEDIA_ROOT, 'qrcodes', f'{numero_attestation}.png')
    img.save(path)
    return f'qrcodes/{numero_attestation}.png'


def journaliser(utilisateur, action, detail=''):
    from .models import JournalAction
    try:
        JournalAction.objects.create(
            utilisateur=utilisateur,
            action=action,
            detail=detail
        )
    except Exception:
        pass