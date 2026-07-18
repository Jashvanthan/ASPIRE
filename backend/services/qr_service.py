"""
backend/services/qr_service.py
--------------------------------
Service for generating QR codes.
"""

import qrcode
import io

class QRService:
    @staticmethod
    def generate_qr_bytes(data: str) -> bytes:
        """
        Generate a QR code image as PNG bytes.
        
        Args:
            data: The string data to encode (e.g., student_id).
            
        Returns:
            The generated PNG image as raw bytes.
        """
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_H,
            box_size=10,
            border=4,
        )
        qr.add_data(data)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        img_io = io.BytesIO()
        img.save(img_io, 'PNG')
        return img_io.getvalue()
