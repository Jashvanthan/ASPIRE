"""
backend/services/email_service.py
---------------------------------
Service for sending emails asynchronously.
"""

import logging
import smtplib
import threading
from email.message import EmailMessage

logger = logging.getLogger(__name__)

class EmailService:
    @staticmethod
    def send_qr_email_async(app, email_address: str, student_name: str, qr_bytes: bytes):
        """
        Send the 2FA QR code to the student asynchronously.
        Requires the Flask app instance to access configuration outside the request context.
        """
        def send_email():
            with app.app_context():
                server = app.config.get("SMTP_SERVER")
                port = app.config.get("SMTP_PORT")
                username = app.config.get("SMTP_USERNAME")
                password = app.config.get("SMTP_PASSWORD")
                sender = app.config.get("MAIL_DEFAULT_SENDER")
                
                if not username or not password:
                    logger.warning("SMTP credentials not configured. Skipping email delivery.")
                    return
                
                try:
                    msg = EmailMessage()
                    msg['Subject'] = 'Welcome to SmartAttend - Your 2FA QR Code'
                    msg['From'] = sender
                    msg['To'] = email_address
                    
                    msg.set_content(f"""
Hello {student_name},

Welcome to SmartAttend! Your registration was successful.

Attached is your Two-Factor Authentication (2FA) QR Code.
Please save this image on your phone. You will need to show it to the camera during live attendance to verify your identity.

Best regards,
The SmartAttend Team
                    """)
                    
                    msg.add_attachment(
                        qr_bytes,
                        maintype='image',
                        subtype='png',
                        filename=f'{student_name.replace(" ", "_")}_QR.png'
                    )
                    
                    with smtplib.SMTP(server, port) as smtp:
                        smtp.starttls()
                        smtp.login(username, password)
                        smtp.send_message(msg)
                        
                    logger.info(f"Successfully sent QR email to {email_address}")
                except Exception as e:
                    logger.error(f"Failed to send email to {email_address}: {e}")
                    
        # Start background thread
        thread = threading.Thread(target=send_email)
        thread.daemon = True
        thread.start()
