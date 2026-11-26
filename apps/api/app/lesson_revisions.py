"""Small correction for a published lesson that repeats its own quiz answer.

Students receive the concise version until an editor stores it as a normal,
versioned lesson update. Editors can see and apply the proposed text.
"""

COURSE_TITLE = "Análisis de datos para decisiones"
LESSON_TITLE = "De una pregunta de negocio a un indicador confiable"
LEAKED_EXAMPLE = "Si hubo 20 ventas y 100 consultas"

CONCISE_CONTENT = """Objetivo
Compara canales con un indicador claro y datos revisados.

Antes de calcular
• Define el periodo y qué cuenta como consulta o venta válida.
• Revisa duplicados y datos faltantes.
• Calcula la conversión: ventas confirmadas ÷ consultas válidas × 100.

Práctica
Compara dos canales y explica cuál obtuvo mejor resultado. Incluye una limitación de los datos."""


def lesson_content_for_view(course_title: str, lesson_title: str, stored_content: str, editor: bool):
    if course_title == COURSE_TITLE and lesson_title == LESSON_TITLE and LEAKED_EXAMPLE in stored_content:
        return (stored_content, CONCISE_CONTENT) if editor else (CONCISE_CONTENT, None)
    return stored_content, None
