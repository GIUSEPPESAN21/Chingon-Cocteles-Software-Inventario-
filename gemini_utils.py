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
                # Check model existence and capability before full initialization if possible
                # For now, rely on try-except with GenerativeModel
                model = genai.GenerativeModel(model_name)
                # Perform a simple test generation to confirm compatibility (optional but recommended)
                # try:
                #    model.generate_content("test", generation_config=genai.types.GenerationConfig(max_output_tokens=1))
                # except Exception as test_e:
                #    logger.warning(f"⚠️ Modelo '{model_name}' inicializado pero falló prueba de generación: {test_e}")
                #    continue # Try next model if basic generation fails

                logger.info(f"✅ Modelo de Gemini '{model_name}' inicializado con éxito.")
                return model
            except google.api_core.exceptions.NotFound:
                 logger.warning(f"⚠️ Modelo '{model_name}' no encontrado (NotFound).")
                 continue # Specific handling for NotFound
            except Exception as e:
                logger.warning(f"⚠️ Modelo '{model_name}' no disponible o no compatible: {e}")
                continue

        # If loop completes without returning, no model was initialized
        raise Exception("No se pudo inicializar ningún modelo de Gemini compatible de la lista. Verifica tu API Key y los nombres de los modelos.")


    def generate_daily_report(self, orders: list):
        """
        Generates a daily sales report as a JSON string with recommendations.
        """
        if not self.model:
            return json.dumps({"error": "El modelo de texto no está inicializado."}) # Return JSON error
        if not orders:
            # Return a JSON structure indicating no data, not just a string
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
                if isinstance(quantity, (int, float)) and quantity > 0: # Ensure valid quantity
                    item_sales[item_name] = item_sales.get(item_name, 0) + quantity

        top_selling_items = sorted(item_sales.items(), key=lambda x: x[1], reverse=True)

        # Build prompt requesting JSON output
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

        **IMPORTANTE:** Tu única salida debe ser el objeto JSON válido. No incluyas NADA antes o después del JSON, ni explicaciones, ni las marcas ```json. Asegúrate de que las strings dentro del JSON usen comillas dobles y que las listas sean arrays JSON válidos (ej: ["obs1", "obs2"]).
        """

        try:
            # Configure generation for JSON output if API supports it, otherwise rely on prompt
            # generation_config = genai.types.GenerationConfig(response_mime_type="application/json") # Might not be supported by all models/versions
            # response = self.model.generate_content(prompt, generation_config=generation_config)
            response = self.model.generate_content(prompt) # Default text generation


            # Robust JSON extraction and validation
            if response and response.text:
                 clean_text = response.text.strip()
                 # Try to find JSON block, removing potential markdown backticks
                 json_start = clean_text.find('{')
                 json_end = clean_text.rfind('}') + 1

                 if json_start != -1 and json_end != 0:
                     json_str = clean_text[json_start:json_end]
                     try:
                         # Validate it's proper JSON
                         json.loads(json_str)
                         # Check if essential keys are present (basic validation)
                         temp_data = json.loads(json_str)
                         if all(k in temp_data for k in ['resumen_ejecutivo', 'observaciones_clave', 'recomendaciones_estrategicas', 'elaborado_por']):
                            return json_str # Return the valid JSON string
                         else:
                             logger.warning("IA devolvió JSON pero faltan claves esperadas.")
                             return json.dumps({"error": "La IA devolvió un JSON incompleto.", "raw_response": clean_text})

                     except json.JSONDecodeError:
                          logger.error("IA devolvió un JSON mal formado.")
                          return json.dumps({"error": "La IA devolvió un JSON mal formado.", "raw_response": clean_text})
                 else:
                     logger.error("No se encontró un objeto JSON en la respuesta de la IA.")
                     return json.dumps({"error": "No se encontró un objeto JSON en la respuesta de la IA.", "raw_response": clean_text})
            else:
                 logger.error("La IA no devolvió una respuesta válida.")
                 return json.dumps({"error": "La IA no devolvió una respuesta válida."})

        except Exception as e:
            logger.error(f"Error crítico durante la generación de reporte con Gemini: {e}")
            error_message = str(e)
            # Specific error check
            if "API key not valid" in error_message:
                return json.dumps({"error": "La API Key de Gemini no es válida. Verifícala en los secretos."})
            # General error
            return json.dumps({"error": f"No se pudo generar el reporte: {error_message}"})


    def analyze_image(self, image_pil: Image, description: str = ""):
        """
        Analiza una imagen y devuelve una respuesta JSON estructurada y limpia.
        (Kept for potential future use, ensure vision model is compatible)
        """
        if not self.model: # Assuming the selected model is multimodal
            return json.dumps({"error": "El modelo de Gemini no está inicializado."})

        try:
            prompt = f"""
            Analiza esta imagen de un objeto de inventario.
            Descripción adicional del sistema de detección: "{description}"

            Actúa como un experto catalogador. Tu única salida debe ser un objeto JSON válido con estas claves:
            - "elemento_identificado": (string) El nombre específico y descriptivo del objeto.
            - "cantidad_aproximada": (integer) El número de unidades que ves. Si es solo uno, pon 1.
            - "estado_condicion": (string) La condición aparente (ej: "Nuevo en empaque", "Usado", "Componente").
            - "caracteristicas_distintivas": (string) Lista separada por comas de características visuales clave.
            - "posible_categoria_de_inventario": (string) La categoría más lógica (ej: "Electrónicos", "Ferretería").
            - "marca_modelo_sugerido": (string) Si es visible, marca y/o modelo (ej: "Sony XM4"). Si no, "No visible".

            IMPORTANTE: Responde solo con el objeto JSON válido, sin texto adicional ni marcas ```json.
            """

            # Assuming the initialized model can handle image input
            response = self.model.generate_content([prompt, image_pil])

            # Robust JSON extraction (similar to report generation)
            if response and response.text:
                clean_text = response.text.strip()
                json_start = clean_text.find('{')
                json_end = clean_text.rfind('}') + 1
                if json_start != -1 and json_end != 0:
                    json_str = clean_text[json_start:json_end]
                    try:
                        json.loads(json_str) # Validate JSON
                        # Basic check for expected keys
                        temp_data = json.loads(json_str)
                        if "elemento_identificado" in temp_data:
                            return json_str
                        else:
                             return json.dumps({"error": "JSON de imagen incompleto.", "raw_response": clean_text})
                    except json.JSONDecodeError:
                         return json.dumps({"error": "JSON de imagen mal formado.", "raw_response": clean_text})
                else:
                    return json.dumps({"error": "No se encontró JSON en respuesta de imagen.", "raw_response": clean_text})
            else:
                return json.dumps({"error": "Respuesta de imagen inválida."})

        except Exception as e:
            logger.error(f"Error crítico durante el análisis de imagen con Gemini: {e}")
            return json.dumps({"error": f"No se pudo contactar al servicio de IA para imagen: {str(e)}"})
