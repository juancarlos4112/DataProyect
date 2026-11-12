# -*- coding: utf-8 -*-
"""Catálogos fijos de la orden de servicio."""

CHECKLIST = [
    ("limpieza", "Limpieza general del rack y equipos"),
    ("cables", "Ordenamiento y peinado de cables"),
    ("conexiones", "Revisión de conexiones y etiquetado"),
    ("energia", "Revisión de UPS y respaldo de energía"),
    ("temperatura", "Revisión de temperatura y ventilación"),
    ("conectividad", "Prueba de conectividad y enlaces"),
    ("alarmas", "Revisión de logs y alarmas"),
    ("documentacion", "Actualización de inventario y documentación"),
]

CHECKLIST_KEYS = {k for k, _ in CHECKLIST}

CHECKLIST_LABELS = dict(CHECKLIST)

STATUS_LABELS = {"ok": "OK", "obs": "Con observación", "na": "N/A"}

ORDER_TYPES = {
    "preventiva": "Mantención preventiva",
    "correctiva": "Mantención correctiva",
    "emergencia": "Emergencia",
}
