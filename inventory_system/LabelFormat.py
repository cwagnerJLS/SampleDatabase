from reportlab.lib.pagesizes import inch
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from io import BytesIO
import qrcode


# Convert mm to points for ReportLab
def mm_to_points(mm_value):
    return mm_value * (72 / 25.4)


def generate_label(output_path, qr_data, id_value, date_received, rsm_value, description):
    # Create a canvas for the label
    label_width = mm_to_points(101.6)
    label_height = mm_to_points(50.8)
    c = canvas.Canvas(output_path, pagesize=(label_width, label_height))

    # Generate a QR code and add it to the PDF
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=1)
    qr.add_data(qr_data)
    qr.make(fit=True)

    # Convert the QR code to an image
    img = qr.make_image(fill='black', back_color='white')

    # Convert the PIL Image to a BytesIO object
    img_buffer = BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)

    # Use ImageReader with the BytesIO object
    img_reader = ImageReader(img_buffer)

    # Define the margins and calculate the QR code size and position
    margin = mm_to_points(5)  # 5mm margin
    qr_x = label_width / 2 + margin  # Start slightly to the right of the center
    qr_y = margin  # Start a bit above the bottom margin
    qr_width = label_width / 2 - 2 * margin  # QR code takes up the remaining width with margins
    qr_height = label_height - 2 * margin  # QR code height with top and bottom margin

    # Draw the QR code on the right half of the label
    c.drawImage(img_reader, qr_x, qr_y, qr_width, qr_height)

    # Set font for the text
    font_bold = "Helvetica-Bold"
    font_regular = "Helvetica"
    font_size = mm_to_points(4)

    # Combine the bold and regular text for ID
    id_text = "ID: "

    # Calculate the total width of the ID text
    c.setFont(font_bold, font_size)
    id_text_width = c.stringWidth(id_text)
    c.setFont(font_regular, font_size)
    id_value_width = c.stringWidth(id_value)
    total_id_text_width = id_text_width + id_value_width

    # Define the offset for shifting the text to the right
    right_shift_offset = mm_to_points(2)  # Adjust this value as needed

    # Adjust the starting X position for the ID text
    left_half_width = (label_width / 2) - (2 * margin)
    start_x_id = margin + (left_half_width - total_id_text_width) / 2 + right_shift_offset

    # Draw the ID text (centered horizontally in the left half, shifted to the right)
    c.setFont(font_bold, font_size)
    c.drawString(start_x_id, label_height - margin - mm_to_points(2), id_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_id + id_text_width, label_height - margin - mm_to_points(2), id_value)

    # Combine the bold and regular text for Date Received
    date_text = "Date Received: "

    # Calculate the total width of the Date Received text
    c.setFont(font_bold, font_size)
    date_text_width = c.stringWidth(date_text)
    c.setFont(font_regular, font_size)
    date_value_width = c.stringWidth(date_received)
    total_date_text_width = date_text_width + date_value_width

    # Adjust the starting X position for the Date Received text
    start_x_date = margin + (left_half_width - total_date_text_width) / 3 + right_shift_offset

    # Draw the Date Received text (centered horizontally in the left half, shifted to the right)
    c.setFont(font_bold, font_size)
    c.drawString(start_x_date, label_height - margin - mm_to_points(8), date_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_date + date_text_width, label_height - margin - mm_to_points(8), date_received)

    # Combine the bold and regular text for RSM
    rsm_text = "RSM: "

    # Calculate the total width of the RSM text
    c.setFont(font_bold, font_size)
    rsm_text_width = c.stringWidth(rsm_text)
    c.setFont(font_regular, font_size)
    rsm_value_width = c.stringWidth(rsm_value)
    total_rsm_text_width = rsm_text_width + rsm_value_width

    # Adjust the starting X position for the RSM text
    start_x_rsm = margin + (left_half_width - total_rsm_text_width) / 2 + right_shift_offset

    # Draw the RSM text (directly under the Date Received text)
    c.setFont(font_bold, font_size)
    c.drawString(start_x_rsm, label_height - margin - mm_to_points(14), rsm_text)
    c.setFont(font_regular, font_size)
    c.drawString(start_x_rsm + rsm_text_width, label_height - margin - mm_to_points(14), rsm_value)

    # Add the additional wrapped text
    styles = getSampleStyleSheet()
    normal_style = styles['Normal']
    normal_style.fontName = font_regular
    normal_style.fontSize = font_size
    normal_style.leading = font_size * 1.2
    normal_style.alignment = 1  # Center alignment

    # Create a Paragraph for text wrapping
    wrapped_paragraph = Paragraph(description, normal_style)

    # Set the maximum width for the text to avoid overlap with QR code
    max_text_width = label_width / 2 - 2 * margin

    # Define the position for the wrapped text, just below the RSM text
    text_x = margin
    text_y = margin + mm_to_points(5)  # Adjust this value to place it correctly

    # Draw the wrapped text on the canvas
    c.translate(text_x, text_y)
    wrapped_paragraph.wrapOn(c, max_text_width, label_height)
    wrapped_paragraph.drawOn(c, 0, 0)

    # Finalize the PDF
    c.save()


# Example usage
if __name__ == "__main__":
    output_path = r"C:\Users\cwagner\Desktop\Temp\label.pdf"
    qr_data = "Test"  # This could be a URL or any other data to encode in the QR code
    id_value = "7133"
    date_received = "2024-07-17"
    rsm_value = "Jeremy Rothermel"
    description = "8070 - Henry's Street Pretzels - Biglerville, PA - Talon Variovac Loading for So"

    generate_label(output_path, qr_data, id_value, date_received, rsm_value, description)
