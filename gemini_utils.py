import google.generativeai as genai
import logging
from PIL import Image
import streamlit as st
import json
from datetime import datetime

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
        # This will find the best available multimodal model for both text and vision
        self.model = self._get_available_model()
    
    def _get_available_model(self):
        """
        Intenta inicializar el mejor modelo de Gemini disponible de la lista proporcionada.
        """
        # Lista de modelos priorizada, AHORA INCLUYE el modelo experimental.
        model_candidates = [
            "gemini-2.0-flash-exp",       # Modelo experimental más reciente (prioridad 1)
            "gemini-1.5-flash-latest",    # Versión más reciente y rápida de 1.5
            "gemini-1.5-pro-latest",      # Versión Pro más reciente de 1.5
            "gemini-1.5-flash",           # Modelo Flash básico
            "gemini-1.5-pro",             # Modelo Pro básico
        ]
        
        for model_name in model_candidates:
            try:
                model = genai.GenerativeModel(model_name)
                logger.info(f"✅ Modelo de Gemini '{model_name}' inicializado con éxito.")
                return model
            except Exception as e:
                logger.warning(f"⚠️ Modelo '{model_name}' no disponible o no compatible: {e}")
                continue
        
        raise Exception("No se pudo inicializar ningún modelo de Gemini compatible. Verifica tu API Key.")

    def generate_daily_report(self, orders: list):
        """
        Generates a daily sales report with recommendations based on the provided orders.
        """
        if not self.model:
            return "### Error\nEl modelo de texto no está inicializado."
        if not orders:
            return "No hay ventas que reportar para el día de hoy."

        total_revenue = sum(o.get('price', 0) for o in orders)
        total_orders = len(orders)
        
        item_sales = {}
        for order in orders:
            for item in order.get('ingredients', []):
                item_name = item.get('name', 'N/A')
                quantity = item.get('quantity', 0)
                item_sales[item_name] = item_sales.get(item_name, 0) + quantity

        top_selling_items = sorted(item_sales.items(), key=lambda x: x[1], reverse=True)

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
        1.  Un **Resumen Ejecutivo** breve.
        2.  Una lista de **Observaciones Clave** (2-3 puntos).
        3.  Una lista de **Recomendaciones Estratégicas** (2-3 puntos).
        4.  Al final del todo, una firma con los datos exactos que se proporcionan a continuación.

        **Formato de Salida Esperado (Usa este formato Markdown exacto):**
        
        ### 📈 Reporte de Desempeño Diario
        
        #### Resumen Ejecutivo
        * [Tu resumen conciso del rendimiento del día aquí]
        
        #### Observaciones Clave
        * [Observación 1 sobre los productos más vendidos o patrones]
        * [Observación 2]
        
        #### Recomendaciones Estratégicas
        * [Recomendación 1 clara y práctica]
        * [Recomendación 2]
        
        ---
        
        **Elaborado por:**
        Joseph Javier Sánchez Acuña
        CEO - SAVA SOFTWARE FOR ENGINEERING
        """
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            logger.error(f"Error crítico durante la generación de reporte con Gemini: {e}")
            error_message = str(e)
            if "API key not valid" in error_message:
                return "### Error\nLa API Key de Gemini no es válida. Por favor, verifícala en los secretos de Streamlit."
            return f"### Error\nNo se pudo generar el reporte: {error_message}"

    def analyze_image(self, image_pil: Image, description: str = ""):
        """
        Analiza una imagen y devuelve una respuesta JSON estructurada y limpia.
        """
        if not self.model:
            return json.dumps({"error": "El modelo de visión no está inicializado."})

        try:
            prompt = f"""
            Analiza esta imagen de un objeto de inventario.
            Descripción adicional del sistema de detección: "{description}"
            
            Actúa como un experto catalogador. Tu única salida debe ser un objeto JSON válido con estas claves:
            - "elemento_identificado": (string) El nombre específico y descriptivo del objeto.
            - "cantidad_aproximada": (integer) El número de unidades que ves. Si es solo uno, pon 1.
            - "estado_condicion": (string) La condición aparente (ej: "Nuevo en empaque", "Usado, con ligeras marcas", "Componente individual").
            - "caracteristicas_distintivas": (string) Una lista separada por comas de características visuales clave (ej: "Color rojo, carcasa metálica, conector USB-C").
            - "posible_categoria_de_inventario": (string) La categoría más lógica (ej: "Componentes Electrónicos", "Ferretería", "Material de Oficina").
            - "marca_modelo_sugerido": (string) Si es visible, la marca y/o modelo del objeto (ej: "Sony WH-1000XM4"). Si no, pon "No visible".

            IMPORTANTE: Responde solo con el objeto JSON, sin texto adicional, explicaciones, ni las marcas ```json.
            """
            
            response = self.model.generate_content([prompt, image_pil])
            
            # Limpieza robusta de la respuesta para extraer solo el JSON.
            if response and response.text:
                clean_text = response.text.strip().replace("```json", "").replace("```", "")
                try:
                    # Validar si es un JSON válido antes de devolver
                    json.loads(clean_text)
                    return clean_text
                except json.JSONDecodeError:
                     return json.dumps({"error": "La IA devolvió un JSON mal formado.", "raw_response": clean_text})
            else:
                return json.dumps({"error": "La IA no devolvió una respuesta válida."})
                
        except Exception as e:
            logger.error(f"Error crítico durante el análisis de imagen con Gemini: {e}")
            return json.dumps({"error": f"No se pudo contactar al servicio de IA: {str(e)}"})
