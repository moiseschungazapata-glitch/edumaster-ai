"""Small, self-contained PDF for a verifiable course completion certificate."""
from datetime import datetime


def render_certificate(course: str, student: str, code: str, issued_at: datetime, verification_url: str, heading: str = "Certificado de finalización", signatory: str = "EduMaster.ai") -> bytes:
    # Escape PDF string operators; Latin-1 replacement keeps this dependency-free on Vercel.
    def pdf_text(value: str) -> str:
        return value.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = [
        ("EDUMASTER.AI", 30, 190, 690),
        (heading, 22, 100, 585),
        ("Se certifica que", 14, 180, 520),
        (student, 18, 100, 480),
        ("completo satisfactoriamente el curso", 14, 125, 430),
        (course, 18, 100, 390),
        (f"Emitido: {issued_at:%d/%m/%Y}", 12, 180, 300),
        (f"Emitido por: {signatory}", 12, 180, 275),
        (f"Codigo de verificacion: {code}", 10, 90, 250),
        (f"Verificar en: {verification_url}", 8, 40, 225),
    ]
    stream = ("\n".join(f"BT /F1 {size} Tf 0.1 0.2 0.4 rg 1 0 0 1 {x} {y} Tm ({pdf_text(value)}) Tj ET" for value, size, x, y in lines) + "\n").encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + obj + b"\nendobj\n")
    xref = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return bytes(output)
