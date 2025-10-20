import google.generativeai as genai
import logging
import streamlit as st
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GeminiUtils:
    def __init__(self):
        """
        Initializes the Gemini client for text generation.
        """
        self.api_key = st.secrets.get('GEMINI_API_KEY')
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in Streamlit secrets")
        
        genai.configure(api_key=self.api_key)
        
        # Using a stable, specific model name instead of the "-latest" tag
        # to ensure compatibility with the library version.
        self.model_name = "gemini-1.5-flash"
        try:
            self.model = genai.GenerativeModel(self.model_name)
            logger.info(f"✅ Text model '{self.model_name}' initialized successfully.")
        except Exception as e:
            logger.error(f"⚠️ Could not initialize model '{self.model_name}': {e}")
            raise Exception("Could not initialize any compatible Gemini text model. Please check your API Key.")

    def generate_daily_report(self, orders: list):
        """
        Generates a daily sales report with recommendations based on the provided orders.
        """
        if not orders:
            return "No hay ventas que reportar para el día de hoy."

        # Prepare data for the prompt
        total_revenue = sum(o.get('price', 0) for o in orders)
        total_orders = len(orders)
        
        item_sales = {}
        for order in orders:
            for item in order.get('ingredients', []):
                item_name = item.get('name', 'N/A')
                quantity = item.get('quantity', 0)
                item_sales[item_name] = item_sales.get(item_name, 0) + quantity

        top_selling_items = sorted(item_sales.items(), key=lambda x: x[1], reverse=True)

        # Build the prompt
        prompt = f"""
        **Actúa como un analista de negocios experto para una tienda.**
        
        **Fecha del Reporte:** {datetime.now().strftime('%d de %B de %Y')}
        
        **Datos de Ventas del Día:**
        * **Ingresos Totales:** ${total_revenue:,.2f}
        * **Número de Pedidos:** {total_orders}
        * **Artículos Vendidos:**
        """
        for name, qty in top_selling_items:
            prompt += f"    * {name}: {qty} unidades\n"

        prompt += """
        **Tu Tarea:**
        Basado en los datos de ventas de hoy, escribe un reporte conciso y accionable en formato Markdown. El reporte debe incluir:
        1.  **Resumen Ejecutivo:** Un párrafo breve que resuma el rendimiento del día.
        2.  **Observaciones Clave:** Una lista de 2-3 puntos destacando los productos más vendidos o cualquier patrón interesante.
        3.  **Recomendaciones Estratégicas:** Una lista de 2-3 recomendaciones claras y prácticas para el negocio. Por ejemplo, sugerir promociones para artículos populares, ajustar el stock, o crear combos.

        **Formato de Salida Esperado (Solo Markdown):**
        
        ### 📈 Reporte de Desempeño Diario
        
        #### Resumen Ejecutivo
        * [Tu resumen aquí]
        
        #### Observaciones Clave
        * [Observación 1]
        * [Observación 2]
        
        #### Recomendaciones Estratégicas
        * [Recomendación 1]
        * [Recomendación 2]
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error crítico durante la generación de reporte con Gemini: {e}")
            # The error message from the API is now more user-friendly
            error_message = str(e)
            if "API key not valid" in error_message:
                return "### Error\nLa API Key de Gemini no es válida. Por favor, verifícala en los secretos de Streamlit."
            return f"### Error\nNo se pudo generar el reporte: {error_message}"

