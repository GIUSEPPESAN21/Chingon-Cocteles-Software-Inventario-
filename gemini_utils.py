import google.generativeai as genai
import logging
from PIL import Image
import streamlit as st
import json
from datetime import datetime, timezone
import google.api_core.exceptions

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiUtils:
    def __init__(self):
        """
        Initializes the Gemini client by finding the best available model.
        """
        self.api_key = st.secrets.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY no encontrada en los secrets de Streamlit")

        genai.configure(api_key=self.api_key)
        self.model = self._get_available_model()

    def _get_available_model(self):
        """
        Intenta inicializar el mejor modelo de Gemini disponible de la lista proporcionada.
        """
        model_candidates = [
            "gemini-1.5-flash-latest",
            "gemini-1.5-pro-latest",
        ]

        for model_name in model_candidates:
            try:
                model = genai.GenerativeModel(model_name)
                logger.info(f"✅ Modelo de Gemini '{model_name}' inicializado con éxito.")
                return model
            except google.api_core.exceptions.NotFound:
                 logger.warning(f"⚠️ Modelo '{model_name}' no encontrado (NotFound).")
                 continue
            except Exception as e:
                logger.warning(f"⚠️ Modelo '{model_name}' no disponible o no compatible: {e}")
                continue

        raise Exception("No se pudo inicializar ningún modelo de Gemini compatible de la lista.")


    def generate_daily_report(self, orders: list):
        """
        Generates a daily sales report as a JSON string with recommendations.
        """
        if not self.model:
            return json.dumps({"error": "El modelo de texto no está inicializado."})
        if not orders:
            return json.dumps({
                "resumen_ejecutivo": "No hubo ventas completadas hoy.",
                "observaciones_clave": [],
                "recomendaciones_estrategicas": [],
                "elaborado_por": {
                    "nombre": "Joseph Javier Sánchez Acuña",
                    "cargo": "CEO - SAVA SOFTWARE FOR ENGINEERING"
                },
                "metadata": {"status": "no_data"}
            })

        total_revenue = sum(o.get('price', 0) for o in orders if isinstance(o.get('price'), (int, float)))
        total_orders = len(orders)

        item_sales = {}
        for order in orders:
            for item in order.get('ingredients', []):
                item_name = item.get('name', 'N/A')
                quantity = item.get('quantity', 0)
                if isinstance(quantity, (int, float)) and quantity > 0:
                    item_sales[item_name] = item_sales.get(item_name, 0) + quantity

        top_selling_items = sorted(item_sales.items(), key=lambda x: x[1], reverse=True)

        prompt = f"""
        **Actúa como un analista de negocios experto para una tienda.**

        **Fecha del Reporte:** {datetime.now(timezone.utc).strftime('%d de %B de %Y')}

        **Datos de Ventas del Día:**
        * **Ingresos Totales:** ${total_revenue:,.2f}
        * **Número de Pedidos:** {total_orders}
        * **Artículos Vendidos (Nombre: Cantidad):**
        """
        for name, qty in top_selling_items:
            prompt += f"    * {name}: {qty}\n"

        prompt += """
        **Tu Tarea:**
        Basado EXCLUSIVAMENTE en los datos de ventas proporcionados para el día de hoy, genera un objeto JSON.
        El JSON debe tener las siguientes claves EXACTAS:
        - "resumen_ejecutivo": (string) Un párrafo MUY CORTO (1-2 frases) resumiendo el rendimiento del día (ingresos y número de pedidos).
        - "observaciones_clave": (array of strings) Una lista con 2 o 3 puntos cortos destacando los productos más vendidos o algún patrón MUY OBVIO de los datos. Sé conciso. No inventes patrones si no los ves claramente.
        - "recomendaciones_estrategicas": (array of strings) Una lista con 2 o 3 recomendaciones CORTAS, CLARAS y ACCIONABLES directamente relacionadas con las observaciones. Ej: "Considerar promoción para [producto más vendido]" o "Evaluar stock de [producto de baja venta]". No des consejos genéricos.
        - "elaborado_por": (object) Un objeto con las claves "nombre" y "cargo" con los siguientes valores fijos:
            - "nombre": "Joseph Javier Sánchez Acuña"
            - "cargo": "CEO - SAVA SOFTWARE FOR ENGINEERING"

        **IMPORTANTE:** Tu única salida debe ser el objeto JSON válido. No incluyas NADA antes o después del JSON, ni explicaciones, ni las marcas 

