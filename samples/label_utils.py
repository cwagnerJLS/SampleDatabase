"""
Utility functions for label generation and QR code creation.
"""
import qrcode
from io import BytesIO
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from .sharepoint_config import LABEL_WIDTH_MM, LABEL_HEIGHT_MM


def mm_to_points(mm_value):
    """Convert millimeters to points for ReportLab."""
    return mm_value * (72 / 25.4)


def generate_qr_code(data):
    """Generate a QR code image from data and return as base64 string."""
    import base64
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    
    # Encode the image to base64 string
    img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
    return img_str


def generate_label(output_path, qr_data, id_value, date_received, rsm_value, description):
    """Generate a PDF label with QR code and sample information."""
    label_width = mm_to_points(LABEL_WIDTH_MM)
    label_height = mm_to_points(LABEL_HEIGHT_MM)
    c = canvas.Canvas(output_path, pagesize=(label_width, label_height))

    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=1)
    qr.add_data(qr_data)
    qr.make(fit=True)

    img = qr.make_image(fill='black', back_color='white')
    img_buffer = BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    img_reader = ImageReader(img_buffer)

    margin = mm_to_points(5)
    qr_x = label_width / 2 + margin
    qr_y = margin
    qr_width = label_width / 2 - 2 * margin
    qr_height = label_height - 2 * margin

    c.drawImage(img_reader, qr_x, qr_y, qr_width, qr_height)

    font_bold = "Helvetica-Bold"
    font_regular = "Helvetica"
    font_size = mm_to_points(4)

    id_text = "ID: "
    c.setFont(font_bold, font_size)
    id_text_width = c.stringWidth(id_text)
    c.setFont(font_regular, font_size)
    id_value_width = c.stringWidth(id_value)
    total_id_text_width = id_text_width + id_value_width

    right_shift_offset = mm_to_points(2)
    left_half_width = (label_width / 2) - (2 * margin)
    start_x_id = margin + (left_half_width - total_id_text_width) / 2 + right_shift_offset

    c.setFont(font_bold, font_size)
    c.drawString(start_x_id, label_height - margin - mm_to_points(2), id_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_id + id_text_width, label_height - margin - mm_to_points(2), id_value)

    date_text = "Date Received: "
    c.setFont(font_bold, font_size)
    date_text_width = c.stringWidth(date_text)
    c.setFont(font_regular, font_size)
    date_value_width = c.stringWidth(date_received)
    total_date_text_width = date_text_width + date_value_width

    start_x_date = margin + (left_half_width - total_date_text_width) / 3 + right_shift_offset

    c.setFont(font_bold, font_size)
    c.drawString(start_x_date, label_height - margin - mm_to_points(8), date_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_date + date_text_width, label_height - margin - mm_to_points(8), date_received)

    rsm_text = "RSM: "
    c.setFont(font_bold, font_size)
    rsm_text_width = c.stringWidth(rsm_text)
    c.setFont(font_regular, font_size)
    rsm_value_width = c.stringWidth(rsm_value)
    total_rsm_text_width = rsm_text_width + rsm_value_width

    start_x_rsm = margin + (left_half_width - total_rsm_text_width) / 2 + right_shift_offset

    c.setFont(font_bold, font_size)
    c.drawString(start_x_rsm, label_height - margin - mm_to_points(14), rsm_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_rsm + rsm_text_width, label_height - margin - mm_to_points(14), rsm_value)

    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    normal_style.fontName = font_regular
    normal_style.fontSize = font_size
    normal_style.leading = font_size * 1.2
    normal_style.alignment = 1

    wrapped_paragraph = Paragraph(description, normal_style)
    max_text_width = label_width / 2 - 2 * margin
    text_left = margin
    text_top = label_height - margin - mm_to_points(20)  # push below RSM

    wrapped_paragraph.wrapOn(c, max_text_width, text_top - margin)
    wrapped_paragraph.drawOn(c, text_left, text_top - wrapped_paragraph.height)

    c.save()