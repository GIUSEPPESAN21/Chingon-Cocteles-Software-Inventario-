# -*- coding: utf-8 -*-
"""
HI-DRIVE: Sistema Avanzado de Gestión de Inventario con IA
Versión 2.1 - Adaptado para Chingon
"""
import streamlit as st
from PIL import Image
import pandas as pd
import plotly.express as px
import json
from datetime import datetime, timedelta, timezone
import numpy as np

# --- Importaciones de utilidades y modelos ---
try:
    from firebase_utils import FirebaseManager
    from gemini_utils import GeminiUtils # Import corrected utility
    from barcode_manager import BarcodeManager 
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
    from twilio.rest import Client
    IS_TWILIO_AVAILABLE = True
except ImportError as e:
    st.error(f"Error de importación: {e}. Asegúrate de que todas las dependencias estén instaladas.")
    st.stop()


# --- CONFIGURACIÓN DE PÁGINA Y ESTILOS ---
st.set_page_config(
    page_title="OSIRIS by SAVA & Chingon",
    page_icon="https://github.com/GIUSEPPESAN21/sava-assets/blob/main/logo_sava.png?raw=true",
    layout="wide"
)

# --- INYECCIÓN DE CSS ---
@st.cache_data
def load_css():
    try:
        with open("style.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.warning("Archivo style.css no encontrado. Se usarán estilos por defecto.")

load_css()

# --- INICIALIZACIÓN DE SERVICIOS (CACHED) ---
@st.cache_resource
def initialize_services():
    try:
        firebase_handler = FirebaseManager()
        barcode_handler = BarcodeManager(firebase_handler)
        gemini_handler = GeminiUtils()
        
        twilio_client = None
        if IS_TWILIO_AVAILABLE and all(k in st.secrets for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN"]):
            twilio_client = Client(st.secrets["TWILIO_ACCOUNT_SID"], st.secrets["TWILIO_AUTH_TOKEN"])
            
        return firebase_handler, gemini_handler, twilio_client, barcode_handler
    except Exception as e:
        st.error(f"**Error Crítico de Inicialización:** {e}")
        return None, None, None, None

firebase, gemini, twilio_client, barcode_manager = initialize_services()

if not all([firebase, gemini, barcode_manager]):
    st.stop()

# --- Funciones de Estado de Sesión ---
def init_session_state():
    defaults = {
        'page': "🏠 Inicio", 'order_items': [],
        'editing_item_id': None, 'scanned_item_data': None,
        'usb_scan_result': None, 'usb_sale_items': []
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_session_state()


# --- LÓGICA DE NOTIFICACIONES ---
def send_whatsapp_alert(message):
    if not twilio_client:
        st.toast("Twilio no configurado. Alerta no enviada.", icon="⚠️")
        return
    try:
        from_number = st.secrets["TWILIO_WHATSAPP_FROM_NUMBER"]
        to_number = st.secrets["DESTINATION_WHATSAPP_NUMBER"]
        twilio_client.messages.create(from_=f'whatsapp:{from_number}', body=message, to=f'whatsapp:{to_number}')
        st.toast("¡Alerta de WhatsApp enviada!", icon="📲")
    except Exception as e:
        st.error(f"Error de Twilio: {e}", icon="🚨")

# --- NAVEGACIÓN PRINCIPAL (SIDEBAR) ---
st.sidebar.image("https://github.com/GIUSEPPESAN21/sava-assets/blob/main/logo_sava.png?raw=true", use_container_width=True)
st.sidebar.markdown('<h1 style="text-align: center; font-size: 2.2rem; margin-top: -20px;">OSIRIS</h1>', unsafe_allow_html=True)
st.sidebar.markdown("<p style='text-align: center; margin-top: -15px;'>by <strong>SAVA</strong> for <strong>Chingon</strong></p>", unsafe_allow_html=True)


PAGES = {
    "🏠 Inicio": "house", 
    "🛰️ Escáner USB": "upc-scan",
    "📦 Inventario": "box-seam",
    "👥 Proveedores": "people", 
    "🛒 Pedidos": "cart4", 
    "📊 Analítica": "graph-up-arrow",
    "📈 Reporte Diario": "clipboard-data",
    "🏢 Acerca de SAVA": "building"
}
for page_name, icon in PAGES.items():
    if st.sidebar.button(f"{page_name}", use_container_width=True, type="primary" if st.session_state.page == page_name else "secondary"):
        st.session_state.page = page_name
        st.session_state.editing_item_id = None
        st.session_state.scanned_item_data = None
        st.session_state.usb_scan_result = None
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.info("© 2025 SAVA & Chingon. Todos los derechos reservados.")

# --- RENDERIZADO DE PÁGINAS ---
if st.session_state.page != "🏠 Inicio":
    st.markdown(f'<h1 class="main-header">{st.session_state.page}</h1>', unsafe_allow_html=True)
    st.markdown("<hr>", unsafe_allow_html=True)


# --- PÁGINAS ---
if st.session_state.page == "🏠 Inicio":
    st.image("https://cdn-icons-png.flaticon.com/512/8128/8128087.png", width=120)
    st.markdown('<h1 class="main-header" style="text-align: left;">Bienvenido a OSIRIS</h1>', unsafe_allow_html=True)
    st.subheader("La solución de gestión de inventario inteligente de SAVA para Chingon")
    st.markdown("""
    **OSIRIS** transforma la manera en que gestionas tu inventario, combinando inteligencia artificial de vanguardia
    con una interfaz intuitiva para darte control, precisión y eficiencia sin precedentes.
    """)
    st.markdown("---")

    st.subheader("Resumen del Negocio en Tiempo Real")
    try:
        items = firebase.get_all_inventory_items()
        orders = firebase.get_orders(status=None)
        suppliers = firebase.get_all_suppliers()
        total_inventory_value = sum(item.get('quantity', 0) * item.get('purchase_price', 0) for item in items)
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("📦 Artículos Únicos", len(items))
        c2.metric("💰 Valor del Inventario", f"${total_inventory_value:,.2f}")
        c3.metric("⏳ Pedidos en Proceso", len([o for o in orders if o.get('status') == 'processing']))
        c4.metric("👥 Proveedores", len(suppliers))
    except Exception as e:
        st.warning(f"No se pudieron cargar las estadísticas: {e}")
    st.markdown("---")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Acciones Rápidas")
        if st.button("🛰️ Usar Escáner USB", use_container_width=True):
             st.session_state.page = "🛰️ Escáner USB"; st.rerun()
        if st.button("📝 Crear Nuevo Pedido", use_container_width=True):
            st.session_state.page = "🛒 Pedidos"; st.rerun()
        if st.button("➕ Añadir Artículo", use_container_width=True):
            st.session_state.page = "📦 Inventario"; st.rerun()
            
    with col2:
        st.subheader("Alertas de Stock Bajo")
        low_stock_items = [item for item in items if item.get('min_stock_alert') and item.get('quantity', 0) <= item.get('min_stock_alert', 0)]
        if not low_stock_items:
            st.success("¡Todo el inventario está por encima del umbral mínimo!")
        else:
            with st.container(height=200):
                for item in low_stock_items:
                    st.warning(f"**{item['name']}**: {item['quantity']} unidades restantes (Umbral: {item['min_stock_alert']})")

elif st.session_state.page == "🛰️ Escáner USB":
    st.info("Conecta tu lector de códigos de barras USB. Haz clic en el campo de texto y comienza a escanear.")

    mode = st.radio("Selecciona el modo de operación:", 
                    ("Gestión de Inventario", "Punto de Venta (Salida Rápida)"), 
                    horizontal=True, key="usb_scanner_mode")

    st.markdown("---")

    if mode == "Gestión de Inventario":
        col1, col2 = st.columns(2)
        with col1:
            st.subheader("Escanear para Gestionar")
            with st.form("usb_inventory_scan_form"):
                barcode_input = st.text_input("Código de Barras", key="usb_barcode_inv", 
                                              help="Haz clic aquí antes de escanear.")
                submitted = st.form_submit_button("Buscar / Registrar", use_container_width=True)
                if submitted and barcode_input:
                    st.session_state.usb_scan_result = barcode_manager.handle_inventory_scan(barcode_input)
                    st.rerun()

        with col2:
            st.subheader("Resultado del Escaneo")
            result = st.session_state.get('usb_scan_result')
            
            if not result:
                st.info("Esperando escaneo...")
            elif result['status'] == 'error':
                st.error(result['message'])
            
            elif result['status'] == 'found':
                item = result['item']
                st.success(f"✔️ Producto Encontrado: **{item['name']}**")
                
                with st.form("update_item_form"):
                    st.write(f"**Stock Actual:** {item.get('quantity', 0)}")
                    st.write(f"**Precio de Venta:** ${item.get('sale_price', 0):.2f}")
                    
                    new_quantity = st.number_input("Nueva Cantidad Total", min_value=0, value=item.get('quantity', 0), step=1)
                    new_price = st.number_input("Nuevo Precio de Venta ($)", min_value=0.0, value=item.get('sale_price', 0.0), format="%.2f")
                    
                    if st.form_submit_button("Actualizar Producto", type="primary", use_container_width=True):
                        updated_data = item.copy()
                        updated_data.update({'quantity': new_quantity, 'sale_price': new_price, 'updated_at': datetime.now().isoformat()})
                        firebase.save_inventory_item(updated_data, item['id'], is_new=False, details="Actualización vía Escáner USB.")
                        st.success(f"¡'{item['name']}' actualizado con éxito!")
                        st.session_state.usb_scan_result = None
                        st.rerun()

            elif result['status'] == 'not_found':
                barcode = result['barcode']
                st.warning(f"⚠️ El código '{barcode}' no existe. Por favor, regístralo.")

                with st.form("create_from_usb_scan_form"):
                    st.markdown(f"**Código de Barras:** `{barcode}`")
                    name = st.text_input("Nombre del Producto")
                    quantity = st.number_input("Cantidad Inicial", min_value=1, step=1)
                    sale_price = st.number_input("Precio de Venta ($)", min_value=0.0, format="%.2f")
                    purchase_price = st.number_input("Precio de Compra ($)", min_value=0.0, format="%.2f")
                    
                    if st.form_submit_button("Guardar Nuevo Producto", type="primary", use_container_width=True):
                        if name and quantity > 0:
                            data = {"name": name, "quantity": quantity, "sale_price": sale_price, "purchase_price": purchase_price, "updated_at": datetime.now().isoformat()}
                            firebase.save_inventory_item(data, barcode, is_new=True, details="Creado vía Escáner USB.")
                            st.success(f"¡Producto '{name}' guardado!")
                            st.session_state.usb_scan_result = None
                            st.rerun()
                        else:
                            st.warning("El nombre y la cantidad son obligatorios.")

    elif mode == "Punto de Venta (Salida Rápida)":
        col1, col2 = st.columns([2, 3])
        with col1:
            st.subheader("Escanear Productos para Venta")
            with st.form("usb_sale_scan_form"):
                barcode_input = st.text_input("Escanear Código de Producto", key="usb_barcode_sale")
                submitted = st.form_submit_button("Añadir a la Venta", use_container_width=True)
                if submitted and barcode_input:
                    updated_list, status_msg = barcode_manager.add_item_to_sale(barcode_input, st.session_state.usb_sale_items)
                    st.session_state.usb_sale_items = updated_list
                    
                    if status_msg['status'] == 'success': st.toast(status_msg['message'], icon="✅")
                    elif status_msg['status'] == 'warning': st.toast(status_msg['message'], icon="⚠️")
                    else: st.error(status_msg['message'])
                    st.rerun()

        with col2:
            st.subheader("Detalle de la Venta Actual")
            if not st.session_state.usb_sale_items:
                st.info("Escanea un producto para comenzar...")
            else:
                total_sale_price = 0
                df_items = []
                for item in st.session_state.usb_sale_items:
                    total_item_price = item['sale_price'] * item['quantity']
                    total_sale_price += total_item_price
                    df_items.append({
                        "Producto": item['name'],
                        "Cantidad": item['quantity'],
                        "Precio Unit.": f"${item['sale_price']:.2f}",
                        "Subtotal": f"${total_item_price:.2f}"
                    })
                
                st.dataframe(pd.DataFrame(df_items), use_container_width=True, hide_index=True)
                st.markdown(f"### Total Venta: `${total_sale_price:,.2f}`")

                c1, c2 = st.columns(2)
                if c1.button("✅ Finalizar y Descontar Stock", type="primary", use_container_width=True):
                    sale_id = f"VentaDirecta-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
                    success, msg, alerts = firebase.process_direct_sale(st.session_state.usb_sale_items, sale_id)
                    if success:
                        st.success(msg)
                        send_whatsapp_alert(f"💸 Venta Rápida Procesada: {sale_id} por un total de ${total_sale_price:,.2f}")
                        for alert in alerts: send_whatsapp_alert(f"📉 ALERTA DE STOCK: {alert}")
                        st.session_state.usb_sale_items = []
                        st.rerun()
                    else:
                        st.error(msg)

                if c2.button("❌ Cancelar Venta", use_container_width=True):
                    st.session_state.usb_sale_items = []
                    st.toast("Venta cancelada.")
                    st.rerun()

elif st.session_state.page == "📦 Inventario":
    if st.session_state.editing_item_id:
        item_to_edit = firebase.get_inventory_item_details(st.session_state.editing_item_id)
        st.subheader(f"✏️ Editando: {item_to_edit.get('name')}")
        with st.form("edit_item_form"):
            suppliers = firebase.get_all_suppliers()
            supplier_map = {s['name']: s['id'] for s in suppliers}
            supplier_names = [""] + list(supplier_map.keys())
            current_supplier = item_to_edit.get('supplier_name')
            current_supplier_index = supplier_names.index(current_supplier) if current_supplier in supplier_names else 0
            name = st.text_input("Nombre del Artículo", value=item_to_edit.get('name'))
            quantity = st.number_input("Cantidad Actual", value=item_to_edit.get('quantity', 0), min_value=0, step=1)
            purchase_price = st.number_input("Costo de Compra ($)", value=item_to_edit.get('purchase_price', 0.0), format="%.2f")
            sale_price = st.number_input("Precio de Venta ($)", value=item_to_edit.get('sale_price', 0.0), format="%.2f")
            min_stock_alert = st.number_input("Umbral de Alerta", value=item_to_edit.get('min_stock_alert', 0), min_value=0, step=1)
            selected_supplier_name = st.selectbox("Proveedor", supplier_names, index=current_supplier_index)
            c1, c2 = st.columns(2)
            if c1.form_submit_button("Guardar Cambios", type="primary", use_container_width=True):
                if name:
                    data = {"name": name, "quantity": quantity, "purchase_price": purchase_price, "sale_price": sale_price,
                            "min_stock_alert": min_stock_alert, "supplier_id": supplier_map.get(selected_supplier_name),
                            "supplier_name": selected_supplier_name, "updated_at": datetime.now().isoformat()}
                    firebase.save_inventory_item(data, st.session_state.editing_item_id, is_new=False, details=f"Edición manual de datos.")
                    st.success(f"Artículo '{name}' actualizado.")
                    st.session_state.editing_item_id = None; st.rerun()
            if c2.form_submit_button("Cancelar", use_container_width=True):
                st.session_state.editing_item_id = None; st.rerun()
    else:
        tab1, tab2 = st.tabs(["📋 Inventario Actual", "➕ Añadir Artículo"])
        with tab1:
            search_query = st.text_input(" Buscar por Nombre o Código/ID", placeholder="Ej: Laptop, 750100100200")
            
            items = firebase.get_all_inventory_items()
            
            if search_query:
                search_query_lower = search_query.lower()
                filtered_items = [
                    item for item in items if 
                    search_query_lower in item.get('name', '').lower() or 
                    search_query_lower in item.get('id', '').lower()
                ]
            else:
                filtered_items = items

            if not filtered_items:
                st.info("No se encontraron productos que coincidan con la búsqueda.")
            else:
                for item in filtered_items:
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
                        c1.markdown(f"**{item.get('name', 'N/A')}**"); c1.caption(f"ID: {item.get('id', 'N/A')}")
                        c2.metric("Stock", item.get('quantity', 0))
                        c3.metric("Precio Venta", f"${item.get('sale_price', 0):,.2f}")
                        if c4.button("✏️", key=f"edit_{item['id']}", help="Editar este artículo"):
                            st.session_state.editing_item_id = item['id']; st.rerun()
        with tab2:
            st.subheader("Añadir Nuevo Artículo al Inventario")
            suppliers = firebase.get_all_suppliers()
            supplier_map = {s['name']: s['id'] for s in suppliers}
            with st.form("add_item_form_new"):
                custom_id = st.text_input("ID Personalizado (SKU)")
                name = st.text_input("Nombre del Artículo")
                quantity = st.number_input("Cantidad Inicial", min_value=0, step=1)
                purchase_price = st.number_input("Costo de Compra ($)", min_value=0.0, format="%.2f")
                sale_price = st.number_input("Precio de Venta ($)", min_value=0.0, format="%.2f")
                min_stock_alert = st.number_input("Umbral de Alerta", min_value=0, step=1)
                selected_supplier_name = st.selectbox("Proveedor", [""] + list(supplier_map.keys()))
                if st.form_submit_button("Guardar Nuevo Artículo", type="primary", use_container_width=True):
                    if custom_id and name and not firebase.get_inventory_item_details(custom_id):
                        data = {"name": name, "quantity": quantity, "purchase_price": purchase_price, "sale_price": sale_price,
                                "min_stock_alert": min_stock_alert, "supplier_id": supplier_map.get(selected_supplier_name),
                                "supplier_name": selected_supplier_name, "updated_at": datetime.now().isoformat()}
                        firebase.save_inventory_item(data, custom_id, is_new=True)
                        st.success(f"Artículo '{name}' guardado.")
                    else:
                        st.error("ID no válido, vacío o ya existente.")

elif st.session_state.page == "👥 Proveedores":
    col1, col2 = st.columns([1, 2])
    with col1:
        with st.form("add_supplier_form", clear_on_submit=True):
            st.subheader("Añadir Proveedor")
            name = st.text_input("Nombre del Proveedor")
            contact = st.text_input("Persona de Contacto")
            email = st.text_input("Email")
            phone = st.text_input("Teléfono")
            if st.form_submit_button("Guardar", type="primary", use_container_width=True):
                if name:
                    firebase.add_supplier({"name": name, "contact_person": contact, "email": email, "phone": phone})
                    st.success(f"Proveedor '{name}' añadido.")
                    st.rerun()
    with col2:
        st.subheader("Lista de Proveedores")
        suppliers = firebase.get_all_suppliers()
        for s in suppliers:
            with st.expander(f"**{s['name']}**"):
                st.write(f"**Contacto:** {s.get('contact_person', 'N/A')}")
                st.write(f"**Email:** {s.get('email', 'N/A')}")
                st.write(f"**Teléfono:** {s.get('phone', 'N/A')}")

elif st.session_state.page == "🛒 Pedidos":
    items_from_db = firebase.get_all_inventory_items()
    
    col1, col2 = st.columns([2, 3])
    with col1:
        st.subheader("Añadir Artículos al Pedido")
        
        add_method = st.radio("Método para añadir:", ("Escanear para Pedido", "Selección Manual"), horizontal=True)
        
        if add_method == "Selección Manual":
            inventory_by_name = {item['name']: item for item in items_from_db if 'name' in item}
            options = [""] + list(inventory_by_name.keys())
            selected_name = st.selectbox("Selecciona un artículo", options)
            if selected_name:
                item_to_add = inventory_by_name[selected_name]
                qty_to_add = st.number_input(f"Cantidad de '{selected_name}'", min_value=1, value=1, step=1, key=f"sel_qty_{item_to_add['id']}")
                if st.button(f"Añadir {qty_to_add} al Pedido", use_container_width=True):
                    st.session_state.order_items, _ = barcode_manager.add_item_to_order_list(item_to_add, st.session_state.order_items, qty_to_add)
                    st.rerun()

        elif add_method == "Escanear para Pedido":
            with st.form("order_scan_form"):
                barcode_input = st.text_input("Escanear Código de Producto", key="order_barcode_scan")
                submitted = st.form_submit_button("Buscar y Añadir", use_container_width=True)

                if submitted and barcode_input:
                    item_data = firebase.get_inventory_item_details(barcode_input)
                    if item_data:
                        st.session_state.order_items, status_msg = barcode_manager.add_item_to_order_list(item_data, st.session_state.order_items, 1)
                        st.toast(status_msg['message'], icon="✅" if status_msg['status'] == 'success' else '⚠️')
                    else:
                        st.error(f"El código '{barcode_input}' no fue encontrado en el inventario.")
                    st.rerun()

    with col2:
        st.subheader("Detalle del Pedido Actual")
        if not st.session_state.order_items:
            st.info("Añade artículos para comenzar un pedido.")
        else:
            total_price = 0
            
            order_df_data = []
            for i, item in enumerate(st.session_state.order_items):
                order_df_data.append({
                    "id": item['id'],
                    "Producto": item['name'],
                    "Cantidad": item['order_quantity'],
                    "Precio Unit.": item.get('sale_price', 0),
                    "Subtotal": item.get('sale_price', 0) * item['order_quantity']
                })
            
            order_df = pd.DataFrame(order_df_data)

            st.write("Puedes editar la cantidad directamente en la tabla:")
            edited_df = st.data_editor(
                order_df,
                column_config={
                    "id": None,
                    "Producto": st.column_config.TextColumn(disabled=True),
                    "Cantidad": st.column_config.NumberColumn(min_value=1, step=1),
                    "Precio Unit.": st.column_config.NumberColumn(format="$%.2f", disabled=True),
                    "Subtotal": st.column_config.NumberColumn(format="$%.2f", disabled=True)
                },
                hide_index=True,
                use_container_width=True,
                key="order_editor"
            )

            # Sincronizar cambios de la tabla al estado de sesión
            if 'edited_rows' in st.session_state.order_editor:
                for idx, changes in st.session_state.order_editor['edited_rows'].items():
                    if idx < len(st.session_state.order_items):
                        st.session_state.order_items[idx]['order_quantity'] = changes.get('Cantidad', st.session_state.order_items[idx]['order_quantity'])

            total_price = sum(item.get('sale_price', 0) * item['order_quantity'] for item in st.session_state.order_items)
            
            st.metric("Precio Total del Pedido", f"${total_price:,.2f}")
            
            order_count = firebase.get_order_count()
            default_title = f"Pedido #{order_count + 1}"
            with st.form("order_form"):
                title = st.text_input("Nombre del Pedido (opcional)", placeholder=default_title)
                final_title = title if title else default_title
                if st.form_submit_button("Crear Pedido", type="primary", use_container_width=True):
                    ingredients = [{'id': item['id'], 'name': item['name'], 'quantity': item['order_quantity']} for item in st.session_state.order_items]
                    order_data = {'title': final_title, 'price': total_price, 'ingredients': ingredients, 'status': 'processing', 'timestamp': datetime.now()}
                    firebase.create_order(order_data)
                    st.success(f"Pedido '{final_title}' creado con éxito.")
                    send_whatsapp_alert(f"🧾 Nuevo Pedido: {final_title} por ${total_price:,.2f}")
                    st.session_state.order_items = []; st.rerun()

    st.markdown("---")
    st.subheader("⏳ Pedidos en Proceso")
    processing_orders = firebase.get_orders('processing')
    if not processing_orders:
        st.info("No hay pedidos en proceso.")
    else:
        for order in processing_orders:
            with st.expander(f"**{order['title']}** - ${order.get('price', 0):,.2f}"):
                st.write("Artículos:")
                for item in order.get('ingredients', []):
                    st.write(f"- {item.get('name')} (x{item.get('quantity')})")
                c1, c2 = st.columns(2)
                if c1.button("✅ Completar Pedido", key=f"comp_{order['id']}", type="primary", use_container_width=True):
                    success, msg, alerts = firebase.complete_order(order['id'])
                    if success:
                        st.success(msg); send_whatsapp_alert(f"✅ Pedido Completado: {order['title']}")
                        for alert in alerts: send_whatsapp_alert(f"📉 ALERTA DE STOCK: {alert}")
                        st.rerun()
                    else: st.error(msg)
                if c2.button("❌ Cancelar Pedido", key=f"canc_{order['id']}", use_container_width=True):
                    firebase.cancel_order(order['id']); st.rerun()

elif st.session_state.page == "📊 Analítica":
    try:
        completed_orders = firebase.get_orders('completed')
        all_inventory_items = firebase.get_all_inventory_items()
    except Exception as e:
        st.error(f"No se pudieron cargar los datos para el análisis: {e}"); st.stop()
    if not completed_orders:
        st.info("No hay pedidos completados para generar analíticas.")
    else:
        tab1, tab2, tab3 = st.tabs(["💰 Rendimiento Financiero", "🔄 Rotación de Inventario", "📈 Predicción de Demanda"])
        with tab1:
            st.subheader("Indicadores Clave de Rendimiento (KPIs)")
            total_revenue = sum(o.get('price', 0) for o in completed_orders)
            total_cogs = sum(ing.get('purchase_price', 0) * ing.get('quantity', 0) for o in completed_orders for ing in o.get('ingredients', []))
            gross_profit = total_revenue - total_cogs
            num_orders = len(completed_orders)
            avg_order_value = total_revenue / num_orders if num_orders > 0 else 0
            profit_margin = (gross_profit / total_revenue) * 100 if total_revenue > 0 else 0
            kpi_cols = st.columns(5)
            kpi_cols[0].metric("Ingresos Totales", f"${total_revenue:,.2f}")
            kpi_cols[1].metric("Beneficio Bruto", f"${gross_profit:,.2f}")
            kpi_cols[2].metric("Margen de Beneficio", f"{profit_margin:.2f}%")
            kpi_cols[3].metric("Pedidos Completados", num_orders)
            kpi_cols[4].metric("Valor Promedio/Pedido", f"${avg_order_value:,.2f}")
            st.markdown("---")
            st.subheader("Tendencia de Ingresos y Beneficios Diarios")
            sales_data = []
            for order in completed_orders:
                if 'timestamp_obj' in order and order['timestamp_obj'] is not None:
                    order_profit = order.get('price', 0) - sum(ing.get('purchase_price', 0) * ing.get('quantity', 0) for ing in order.get('ingredients', []))
                    sales_data.append({'Fecha': order['timestamp_obj'].date(), 'Ingresos': order.get('price', 0), 'Beneficios': order_profit})
            if sales_data:
                df_trends = pd.DataFrame(sales_data).groupby('Fecha').sum()
                st.line_chart(df_trends)
            else:
                st.warning("No hay suficientes datos de fecha para generar un gráfico de tendencias.")
        with tab2:
            all_items_sold = [ing for o in completed_orders for ing in o.get('ingredients', [])]
            item_sales, item_profits = {}, {}
            for item in all_items_sold:
                if 'name' in item:
                    item_sales[item['name']] = item_sales.get(item['name'], 0) + item.get('quantity', 0)
                    profit = (item.get('sale_price', item.get('purchase_price', 0)) - item.get('purchase_price', 0)) * item.get('quantity', 0)
                    item_profits[item['name']] = item_profits.get(item['name'], 0) + profit
            df_sales = pd.DataFrame(list(item_sales.items()), columns=['Artículo', 'Unidades Vendidas']).sort_values('Unidades Vendidas', ascending=False)
            df_profits = pd.DataFrame(list(item_profits.items()), columns=['Artículo', 'Beneficio Generado']).sort_values('Beneficio Generado', ascending=False)
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Top 5 - Artículos Más Vendidos")
                st.dataframe(df_sales.head(5), hide_index=True)
            with col2:
                st.subheader("Top 5 - Artículos Más Rentables")
                st.dataframe(df_profits.head(5), hide_index=True)
            st.markdown("---")
            st.subheader("Inventario de Lenta Rotación (no vendido en los últimos 30 días)")
            thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
            sold_item_ids = {ing['id'] for o in completed_orders if o.get('timestamp_obj') and o['timestamp_obj'].replace(tzinfo=timezone.utc) > thirty_days_ago for ing in o.get('ingredients', [])}
            slow_moving_items = [item for item in all_inventory_items if item['id'] not in sold_item_ids]
            if not slow_moving_items:
                st.success("¡Todos los artículos han tenido movimiento en los últimos 30 días!")
            else:
                for item in slow_moving_items:
                    st.warning(f"- **{item.get('name')}** (Stock actual: {item.get('quantity')})")
        with tab3:
            st.subheader("Predecir Demanda Futura de un Artículo")
            item_names = [item['name'] for item in all_inventory_items if 'name' in item]
            item_to_predict = st.selectbox("Selecciona un artículo:", item_names)
            if item_to_predict:
                sales_history = []
                for order in completed_orders:
                    for item in order.get('ingredients', []):
                        if item.get('name') == item_to_predict and order.get('timestamp_obj'):
                            sales_history.append({'date': order['timestamp_obj'], 'quantity': item['quantity']})
                
                df_hist = pd.DataFrame(sales_history)
                
                if df_hist.empty:
                    st.warning("No hay historial de ventas para este artículo.")
                else:
                    df_hist['date'] = pd.to_datetime(df_hist['date'])
                    df_hist = df_hist.set_index('date').resample('D').sum().fillna(0)

                    MIN_DAYS_FOR_SEASONAL = 14
                    MIN_DAYS_FOR_SIMPLE = 5

                    if len(df_hist) < MIN_DAYS_FOR_SIMPLE:
                        st.warning(f"No hay suficientes datos para una predicción fiable. Se necesitan al menos {MIN_DAYS_FOR_SIMPLE} días de ventas.")
                    else:
                        try:
                            model = None
                            if len(df_hist) >= MIN_DAYS_FOR_SEASONAL:
                                st.info("Datos suficientes. Usando modelo de predicción estacional.")
                                model = ExponentialSmoothing(df_hist['quantity'], seasonal='add', seasonal_periods=7, trend='add').fit()
                            else:
                                st.info("Datos insuficientes para estacionalidad. Usando modelo de tendencia simple.")
                                model = ExponentialSmoothing(df_hist['quantity'], trend='add').fit()
                            
                            prediction = model.forecast(30)
                            prediction[prediction < 0] = 0
                            
                            st.success(f"Se estima una demanda de **{int(round(prediction.sum()))} unidades** para los próximos 30 días.")
                            st.line_chart(prediction)
                        except Exception as e:
                            st.error(f"No se pudo generar la predicción: {e}")

elif st.session_state.page == "📈 Reporte Diario":
    st.info("Genera un reporte de ventas y recomendaciones para el día de hoy utilizando IA.")
    
    if st.button("🚀 Generar Reporte de Hoy", type="primary", use_container_width=True):
        with st.spinner("🧠 La IA está analizando las ventas de hoy y preparando tu reporte..."):
            try:
                today_utc = datetime.now(timezone.utc).date()
                start_of_day = datetime(today_utc.year, today_utc.month, today_utc.day, tzinfo=timezone.utc)
                end_of_day = start_of_day + timedelta(days=1)

                completed_orders_today = firebase.get_orders_in_date_range(start_of_day, end_of_day)

                if not completed_orders_today:
                    st.warning("No hay ventas completadas hoy para generar un reporte.")
                else:
                    report = gemini.generate_daily_report(completed_orders_today)
                    st.markdown(report)

            except Exception as e:
                st.error(f"Ocurrió un error al generar el reporte: {e}")


elif st.session_state.page == "🏢 Acerca de SAVA":
    st.image("https://cdn-icons-png.flaticon.com/512/8128/8128087.png", width=100)
    st.title("Sobre SAVA SOFTWARE")
    st.subheader("Innovación y Tecnología para el Retail del Futuro")
    
    st.markdown("""
    En **SAVA**, somos pioneros en el desarrollo de soluciones de software que fusionan la inteligencia artificial
    con las necesidades reales del sector retail. Nuestra misión es empoderar a los negocios con herramientas
    poderosas, intuitivas y eficientes que transformen sus operaciones y potencien su crecimiento.
    
    Creemos que la tecnología debe ser un aliado, no un obstáculo. Por eso, diseñamos **OSIRIS** pensando
    en la agilidad, la precisión y la facilidad de uso.
    """)
    
    st.markdown("---")
    
    st.subheader("Nuestro Equipo Fundador")
    
    col1, col2 = st.columns([1, 4])
    with col1:
        st.image("https://github.com/GIUSEPPESAN21/sava-assets/blob/main/logo_sava.png?raw=true", width=250, caption="CEO")
    with col2:
        st.markdown("#### Joseph Javier Sánchez Acuña")
        st.markdown("**CEO - SAVA SOFTWARE FOR ENGINEERING**")
        st.write("""
        Líder visionario con una profunda experiencia en inteligencia artificial y desarrollo de software.
        Joseph es el cerebro detrás de la arquitectura de OSIRIS, impulsando la innovación
        y asegurando que nuestra tecnología se mantenga a la vanguardia.
        """)
        st.markdown(
            """
            - **LinkedIn:** [joseph-javier-sánchez-acuña](https://www.linkedin.com/in/joseph-javier-sánchez-acuña-150410275)
            - **GitHub:** [GIUSEPPESAN21](https://github.com/GIUSEPPESAN21)
            """
        )
    st.markdown("---")
    
    st.markdown("##### Cofundadores")
    
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info("**Xammy Alexander Victoria Gonzalez**\n\n*Director Comercial*")
    with c2:
        st.info("**Jaime Eduardo Aragon Campo**\n\n*Director de Operaciones*")
    with c3:
        st.info("**Joseph Javier Sanchez Acuña**\n\n*Director de Proyecto*")

