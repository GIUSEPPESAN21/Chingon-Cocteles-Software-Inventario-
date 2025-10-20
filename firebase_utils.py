import firebase_admin
from firebase_admin import credentials, firestore
import json
import base64
import logging
from datetime import datetime, timezone
import streamlit as st
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Decorator for Firestore operations with retry logic ---
def firestore_retry(func):
    """
    Decorator to add retry logic with exponential backoff to Firestore operations.
    This makes the app more resilient to transient network issues.
    """
    def wrapper(*args, **kwargs):
        max_retries = 3
        delay = 1  # initial delay in seconds
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}. Retrying in {delay}s...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
        logger.error(f"All {max_retries} retries failed for {func.__name__}.")
        # Re-raise the last exception after all retries have failed
        raise
    return wrapper

class FirebaseManager:
    """
    Handles all interactions with Firebase Firestore.
    Ensures that the Firebase app is initialized only once.
    """
    _app_initialized = False

    def __init__(self):
        self.db = None
        self._initialize_firebase()
    
    def _initialize_firebase(self):
        """
        Initializes the Firebase Admin SDK using Streamlit secrets.
        Ensures this process only runs once.
        """
        if not self._app_initialized:
            try:
                creds_base64 = st.secrets.get('FIREBASE_SERVICE_ACCOUNT_BASE64')
                if not creds_base64:
                    raise ValueError("El secret 'FIREBASE_SERVICE_ACCOUNT_BASE64' no fue encontrado.")
                
                creds_json_str = base64.b64decode(creds_base64).decode('utf-8')
                creds_dict = json.loads(creds_json_str)
                
                cred = credentials.Certificate(creds_dict)

                # Only initialize if no apps are present
                if not firebase_admin._apps:
                    firebase_admin.initialize_app(cred)
                    logger.info("Firebase App inicializada correctamente.")
                
                self.__class__._app_initialized = True
            
            except Exception as e:
                logger.error(f"Error fatal al inicializar Firebase: {e}")
                st.error(f"No se pudo conectar a la base de datos. Por favor, verifica los secretos y la configuración. Error: {e}")
                raise

        self.db = firestore.client()

    # --- transactional functions remain outside the class or are called carefully ---

    @firestore_retry
    def save_inventory_item(self, data, custom_id, is_new=False, details=None):
        doc_ref = self.db.collection('inventory').document(custom_id)
        doc_ref.set(data, merge=True)
        history_type = "Stock Inicial" if is_new else "Ajuste Manual"
        details = details or ("Artículo creado en el sistema." if is_new else "Artículo actualizado manualmente.")
        history_data = {
            "timestamp": datetime.now(timezone.utc), "type": history_type,
            "quantity_change": data.get('quantity'), "details": details
        }
        doc_ref.collection('history').add(history_data)
        logger.info(f"Elemento de inventario guardado/actualizado: {custom_id}")

    @firestore_retry
    def get_inventory_item_details(self, doc_id):
        doc = self.db.collection('inventory').document(doc_id).get()
        if doc.exists:
            item = doc.to_dict(); item['id'] = doc.id
            return item
        return None

    @firestore_retry
    def get_all_inventory_items(self):
        docs = self.db.collection('inventory').stream()
        items = [dict(item.to_dict(), **{'id': item.id}) for item in docs]
        return sorted(items, key=lambda x: x.get('name', '').lower())

    # ... (rest of your methods: create_order, get_orders, etc.)
    # The following methods are simplified for brevity but should be included
    
    @firestore_retry
    def get_orders(self, status=None):
        query = self.db.collection('orders')
        if status:
            query = query.where(filter=firestore.FieldFilter('status', '==', status))
        docs = query.stream()
        orders = []
        for doc in docs:
            order = doc.to_dict(); order['id'] = doc.id
            ts = order.get('timestamp')
            if isinstance(ts, datetime):
                order['timestamp_obj'] = ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts
            else:
                order['timestamp_obj'] = datetime.min.replace(tzinfo=timezone.utc)
            orders.append(order)
        return sorted(orders, key=lambda x: x['timestamp_obj'], reverse=True)

    @firestore_retry
    def get_all_suppliers(self):
        docs = self.db.collection('suppliers').stream()
        return sorted([dict(s.to_dict(), **{'id': s.id}) for s in docs], key=lambda x: x.get('name', '').lower())

    def complete_order(self, order_id):
        try:
            transaction = self.db.transaction()
            # Note: You'll need to define how to call the transactional function
            # from within the class context if it's not a static method.
            # For simplicity, keeping it as is assuming it's defined in the global scope.
            # A better approach might be to pass self.db to it.
            return _complete_order_atomic(transaction, self.db, order_id)
        except Exception as e:
            logger.error(f"Fallo la transacción para el pedido {order_id}: {e}")
            return False, f"Error en la transacción: {str(e)}", []
    
    # Add other methods like create_order, process_direct_sale, add_supplier etc.
    # ensuring they use self.db

