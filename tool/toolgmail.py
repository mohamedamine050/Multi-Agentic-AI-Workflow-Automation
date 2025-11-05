# tools/generic_email.py
import os
import smtplib
import asyncio
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

async def send_email(subject: str, body: str, to: str = "tixaf71837@wivstore.com") -> bool:
    """Envoie un email générique avec sujet et corps HTML ou texte."""
    sender_email = os.getenv("GMAIL_USER", "mouhamedamine21072002@gmail.com")
    app_password = os.getenv("GMAIL_APP_PASSWORD", "qvjb qycj ovwt xewe")

    def _send():
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as server:
                server.starttls()
                server.login(sender_email, app_password)

                msg = MIMEMultipart()
                msg["From"] = sender_email
                msg["To"] = to
                msg["Subject"] = subject
                msg.attach(MIMEText(body, "html"))

                server.send_message(msg)
            print(f"✅ Email envoyé à {to} avec sujet '{subject}'.")
            return True
        except Exception as e:
            print(f"❌ Erreur en envoyant email : {e}")
            return False

    return await asyncio.to_thread(_send)
